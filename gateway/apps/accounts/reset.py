"""Password reset by emailed link (FR-ACC-07, FR-ACC-08, FR-ACC-09; API-CONTRACT.md section 9).

1. `request_reset()`: always the same reply. If the email belongs to an active account, a link
   valid for PASSWORD_RESET_LINK_TTL_MINUTES is queued; a new link withdraws the old ones. At
   most PASSWORD_RESET_REQUESTS_PER_ACCOUNT links per account per 15 minutes are sent.
2. `check_link()`: says whether the link still works and whether a TOTP code is needed.
3. `reset_password()`: the new password must pass the password rules. A staff member with an
   authenticator confirms with its code (FR-ACC-09); a wrong code counts towards the sign-in
   lockout, so the reset page cannot be used to guess codes. A reset never removes MFA. On
   success the link is used up, every session of the account ends (FR-ACC-08), the lockout
   is cleared, the change is audited and the holder gets a notice.

Built for staff accounts now; customer accounts (sprint 11) reuse it.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts import mail, signin, tokens
from apps.accounts.models import AccountToken, StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid
from apps.events.models import OutboundEmail

PURPOSE = AccountToken.Purpose.PASSWORD_RESET
REQUEST_WINDOW_MINUTES = 15


def _rules():
    return settings.GATEWAY_RULES


def requested_message() -> str:
    return ("If an account uses this email address, we have sent it a link to reset the "
            f"password. The link works once, for {_rules()['PASSWORD_RESET_LINK_TTL_MINUTES']} "
            "minutes.")


def _audit(action: str, account: StaffAccount, request, **details):
    audit(action, actor_type=AuditEvent.ActorType.STAFF, actor_id=account.public_id,
          merchant_id=account.merchant.public_id if account.merchant else "",
          target_type="staff", target_id=account.public_id,
          request_id=getattr(request, "request_id", ""), details=details)


def request_reset(request, email: str) -> None:
    account = (StaffAccount.objects.select_related("user", "merchant")
               .filter(user__email__iexact=email.strip(), user__is_active=True).first())
    if account is None:
        return
    if tokens.recent_count(account.user, PURPOSE, REQUEST_WINDOW_MINUTES) >= \
            _rules()["PASSWORD_RESET_REQUESTS_PER_ACCOUNT"]:
        return  # same reply, nothing sent
    minutes = _rules()["PASSWORD_RESET_LINK_TTL_MINUTES"]
    ttl = timedelta(minutes=minutes)
    with transaction.atomic():
        token = tokens.issue(account.user, PURPOSE, ttl)
        mail.queue(
            OutboundEmail.Kind.PASSWORD_RESET, account.email, "reset your password",
            "Hello,\n\nSomeone asked to reset the password of your SecurePay dashboard account. "
            f"To choose a new password, open this link within {minutes} minutes:\n\n"
            f"{mail.dashboard_link('reset-password', token)}\n\n"
            "The link works once. If you did not ask for this, ignore this email; your "
            "password stays the same.",
            discard_after=timezone.now() + ttl)
        _audit("staff.password_reset_requested", account, request)


def _account_for(row: AccountToken) -> StaffAccount:
    account = (StaffAccount.objects.select_related("user", "merchant")
               .filter(user=row.user, user__is_active=True).first())
    if account is None:
        raise tokens.link_invalid()
    return account


def check_link(token) -> dict:
    account = _account_for(tokens.peek(PURPOSE, token))
    return {"email": account.email,
            "mfa_required": signin.confirmed_device(account) is not None}


def end_sessions(user) -> int:
    """Delete every stored session of the user (FR-ACC-08). Django would also refuse them on
    the next request, because the password hash in each session no longer matches."""
    ended = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        if str(session.get_decoded().get("_auth_user_id")) == str(user.pk):
            session.delete()
            ended += 1
    return ended


def reset_password(request, token, password, code) -> StaffAccount:
    account = _account_for(tokens.peek(PURPOSE, token))
    if account.is_locked():
        raise signin.locked_error(account)
    if not isinstance(password, str) or not password:
        raise invalid("missing_field", "Enter a new password.", param="password")
    try:
        validate_password(password, account.user)
    except ValidationError as exc:
        raise invalid("weak_password", " ".join(exc.messages), param="password") from None

    device = signin.confirmed_device(account)
    if device is not None:
        code = (code or "").strip().replace(" ", "") if isinstance(code, str) else ""
        if not (len(code) == 6 and code.isdigit() and device.verify_token(code)):
            if signin._record_failure(account, request, "password_reset_totp"):
                raise signin.locked_error(StaffAccount.objects.get(pk=account.pk))
            raise ApiError(401, "code_incorrect", "That code is not right. Enter the current "
                           "6-digit code from your authenticator app.", param="code")

    with transaction.atomic():
        row = tokens.consume(PURPOSE, token)  # a second request with the same link fails here
        user = get_user_model().objects.select_for_update().get(pk=row.user_id)
        user.set_password(password[:256])
        user.save(update_fields=["password"])
        StaffAccount.objects.filter(pk=account.pk).update(failed_attempts=0, locked_until=None)
        # Any other reset link still out there stops working too.
        AccountToken.objects.filter(user=user, purpose=PURPOSE, used_at__isnull=True).update(
            used_at=timezone.now())
        ended = end_sessions(user)
        _audit("staff.password_reset", account, request, sessions_ended=ended,
               mfa_confirmed=device is not None)
        mail.notice(account.email, "your password was changed",
                    "Hello,\n\nThe password of your SecurePay dashboard account was just "
                    "changed, and every signed-in session was ended.\n\nIf this was not you, "
                    "tell an administrator straight away.")
    return account
