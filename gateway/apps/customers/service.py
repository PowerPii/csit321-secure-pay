"""Customer accounts: sign-up, sign-in with lockout, sessions, password change and reset,
payment history (FR-ACC-01 to FR-ACC-04, FR-ACC-07, FR-ACC-08; screens C10 to C12).

Rules, all from GATEWAY_RULES:
* Sign-up: full name, email and a password of at least 12 characters (Django's validators).
  An email that is already registered is refused, as FR-ACC-01 and wireframe C10 say.
* Sign-in: one generic error for an unknown email or a wrong password (FR-ACC-02). The fifth
  wrong password locks sign-in for CUSTOMER_LOCKOUT_MINUTES (FR-ACC-03). While locked,
  nothing is checked.
* Session: a random token in the `sp_customer` cookie (HttpOnly, Secure, SameSite=Strict),
  stored as a keyed hash. It ends after CUSTOMER_IDLE_MINUTES without a request, after
  CUSTOMER_SESSION_MAX_HOURS, on sign-out, and on any password change (FR-ACC-08).
* Password reset: the staff rules (30 minutes, single use, 3 links per 15 minutes, the same
  reply whether or not the email is registered), through the same AccountToken table.
* History: only payments submitted while signed in to this account (FR-ACC-04, FR-ACC-16).
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import mail, tokens
from apps.accounts.models import AccountToken
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid
from apps.customers.history import visible_history
from apps.customers.models import CustomerAccount, CustomerSession
from apps.events.models import OutboundEmail
from apps.payments.models import Payment

COOKIE = "sp_customer"
RESET = AccountToken.Purpose.PASSWORD_RESET
REQUEST_WINDOW_MINUTES = 15
# Hashed once, so an unknown email costs the same time as a wrong password.
_DUMMY_HASH = None


def _rules():
    return settings.GATEWAY_RULES


def _key(token: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"customer:session:{token}".encode(),
                    hashlib.sha256).hexdigest()


def _audit(action: str, customer: CustomerAccount | None, request=None, **details):
    audit(action, actor_type=AuditEvent.ActorType.CUSTOMER,
          actor_id=customer.public_id if customer else "",
          target_type="customer" if customer else "",
          target_id=customer.public_id if customer else "",
          request_id=getattr(request, "request_id", "") if request is not None else "",
          details=details)


def _body_fields(data, allowed: tuple[str, ...]) -> dict:
    if not isinstance(data, dict):
        raise invalid("invalid_json", "The request body must be a JSON object.")
    for name in data:
        if name not in allowed:
            raise invalid("invalid_field", f"Unknown field '{name}'.", param=name)
    return data


def _clean_email(value) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 254:
        raise invalid("invalid_email", "Enter a valid email address.", param="email")
    email = value.strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise invalid("invalid_email", "Enter a valid email address.", param="email") from None
    return email


def _clean_name(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise invalid("missing_field", "Enter your full name.", param="full_name")
    name = " ".join(value.split())
    if len(name) > 100:
        raise invalid("invalid_field", "Use at most 100 characters.", param="full_name")
    return name


def _check_new_password(password, account: CustomerAccount) -> str:
    if not isinstance(password, str) or not password:
        raise invalid("missing_field", "Enter a password.", param="password")
    if len(password) > 256:
        raise invalid("weak_password", "Use at most 256 characters.", param="password")
    try:
        validate_password(password, account)
    except ValidationError as exc:
        raise invalid("weak_password", " ".join(exc.messages), param="password") from None
    return password


def email_taken() -> ApiError:
    return ApiError(409, "email_taken", "This email is already registered. Sign in or reset "
                    "your password.", param="email")


# --- sessions --------------------------------------------------------------------------

def _start_session(customer: CustomerAccount, persistent: bool) -> tuple[str, CustomerSession]:
    now = timezone.now()
    token = secrets.token_urlsafe(32)
    session = CustomerSession.objects.create(
        token_hash=_key(token), customer=customer, last_seen_at=now, persistent=persistent,
        expires_at=now + timedelta(hours=_rules()["CUSTOMER_SESSION_MAX_HOURS"]))
    return token, session


def current_session(token: str | None, touch: bool = True) -> CustomerSession | None:
    """The live session for the cookie, or None. A request keeps it alive (idle limit)."""
    if not token or not isinstance(token, str) or len(token) > 100:
        return None
    session = (CustomerSession.objects.select_related("customer")
               .filter(token_hash=_key(token), ended_at__isnull=True).first())
    if session is None or not session.customer.is_active:
        return None
    now = timezone.now()
    idle = timedelta(minutes=_rules()["CUSTOMER_IDLE_MINUTES"])
    if now >= session.expires_at or now - session.last_seen_at >= idle:
        CustomerSession.objects.filter(pk=session.pk).update(ended_at=now)
        return None
    if touch:
        CustomerSession.objects.filter(pk=session.pk).update(last_seen_at=now)
        session.last_seen_at = now
    return session


def require_session(token: str | None) -> CustomerSession:
    session = current_session(token)
    if session is None:
        raise ApiError(401, "sign_in_required",
                       "Your session has ended. Sign in again to see your account.")
    return session


def end_sessions(customer: CustomerAccount, keep: CustomerSession | None = None) -> int:
    rows = CustomerSession.objects.filter(customer=customer, ended_at__isnull=True)
    if keep is not None:
        rows = rows.exclude(pk=keep.pk)
    return rows.update(ended_at=timezone.now())


def sign_out(token: str | None) -> None:
    if token and isinstance(token, str):
        CustomerSession.objects.filter(token_hash=_key(token), ended_at__isnull=True).update(
            ended_at=timezone.now())


def sign_out_everywhere(session: CustomerSession, request=None) -> int:
    ended = end_sessions(session.customer)
    _audit("customer.signed_out_everywhere", session.customer, request, sessions_ended=ended)
    return ended


# --- sign-up and sign-in ---------------------------------------------------------------

def register(data, request=None) -> tuple[CustomerAccount, str, CustomerSession]:
    """FR-ACC-01. Creates the account and signs it in on this browser."""
    data = _body_fields(data, ("full_name", "email", "password", "remember",
                               "privacy_consent"))
    name = _clean_name(data.get("full_name"))
    email = _clean_email(data.get("email"))
    if data.get("privacy_consent") is not True:  # FR-ACC-12: consent before collecting
        raise invalid("privacy_consent_required", "Agree to the privacy notice to create an "
                      "account.", param="privacy_consent")
    if CustomerAccount.objects.filter(email__iexact=email).exists():
        raise email_taken()
    account = CustomerAccount(email=email, full_name=name)
    password = _check_new_password(data.get("password"), account)
    account.password = make_password(password)
    account.password_changed_at = timezone.now()
    account.privacy_notice_version = _rules()["PRIVACY_NOTICE_VERSION"]
    account.privacy_consent_at = timezone.now()
    try:
        with transaction.atomic():
            account.save()
            account.last_sign_in_at = timezone.now()
            account.save(update_fields=["last_sign_in_at"])
            token, session = _start_session(account, bool(data.get("remember")))
            _audit("customer.registered", account, request)
    except IntegrityError:
        raise email_taken() from None  # two sign-ups with one email at the same moment
    return account, token, session


def invalid_credentials() -> ApiError:
    return ApiError(401, "invalid_credentials", "Email or password is incorrect. After "
                    f"{_rules()['CUSTOMER_LOCKOUT_FAILURES']} failed attempts, sign-in is "
                    f"locked for {_rules()['CUSTOMER_LOCKOUT_MINUTES']} minutes.")


def _record_failure(account: CustomerAccount, request) -> bool:
    now = timezone.now()
    with transaction.atomic():
        account = CustomerAccount.objects.select_for_update().get(pk=account.pk)
        if account.is_locked(now):
            return True
        account.failed_attempts += 1
        locked = account.failed_attempts >= _rules()["CUSTOMER_LOCKOUT_FAILURES"]
        if locked:
            account.locked_until = now + CustomerAccount.lock_duration()
            account.failed_attempts = 0
        account.save(update_fields=["failed_attempts", "locked_until"])
    _audit("customer.sign_in_failed", account, request)
    if locked:
        _audit("customer.locked", account, request, minutes=_rules()["CUSTOMER_LOCKOUT_MINUTES"])
        from apps.security.alerts import raise_alert
        from apps.security.models import AlertKind, Severity

        raise_alert(AlertKind.CUSTOMER_LOCKED, severity=Severity.LOW, source=account.public_id,
                    summary=(f"Customer account {account.public_id} was locked after "
                             f"{_rules()['CUSTOMER_LOCKOUT_FAILURES']} wrong passwords."),
                    details={"stage": "password"})
    return locked


def sign_in(data, request=None) -> tuple[CustomerAccount, str, CustomerSession]:
    """FR-ACC-02, FR-ACC-03."""
    global _DUMMY_HASH
    data = _body_fields(data, ("email", "password", "remember"))
    email, password = data.get("email"), data.get("password")
    if not isinstance(email, str) or not email.strip():
        raise invalid("missing_field", "Enter your email address.", param="email")
    if not isinstance(password, str) or not password:
        raise invalid("missing_field", "Enter your password.", param="password")
    password = password[:256]
    account = (CustomerAccount.objects.filter(email__iexact=email.strip()[:254],
                                              is_active=True).first())
    if account is None:
        if _DUMMY_HASH is None:
            _DUMMY_HASH = make_password(secrets.token_urlsafe(16))
        check_password(password, _DUMMY_HASH)  # same work as a real check
        _audit("customer.sign_in_failed", None, request)
        raise invalid_credentials()
    if account.is_locked():
        # Same reply as a wrong password: sign-in never tells whether an email has an
        # account (security self-test SEC-07, Fifa 18 Nov 2026). The message mentions the
        # lockout, and a password reset still unlocks.
        check_password(password, _DUMMY_HASH or make_password(secrets.token_urlsafe(16)))
        raise invalid_credentials()
    if not check_password(password, account.password):
        _record_failure(account, request)
        raise invalid_credentials()
    with transaction.atomic():
        CustomerAccount.objects.filter(pk=account.pk).update(
            failed_attempts=0, locked_until=None, last_sign_in_at=timezone.now())
        token, session = _start_session(account, bool(data.get("remember")))
        _audit("customer.signed_in", account, request)
    return account, token, session


def me(customer: CustomerAccount) -> dict:
    return {"id": customer.public_id, "full_name": customer.full_name,
            "email": customer.email,
            "idle_minutes": _rules()["CUSTOMER_IDLE_MINUTES"],
            "idle_warning_minutes": _rules()["IDLE_WARNING_MINUTES"]}


# --- personal data: see and correct (FR-ACC-13) -----------------------------------------

def personal_data(customer: CustomerAccount) -> dict:
    """Everything the gateway keeps about the customer as a person. Payments are listed in
    the history; card numbers are never kept (only brand and last four digits)."""
    from apps.common.timefmt import rfc3339

    return {
        "full_name": customer.full_name,
        "email": customer.email,
        "created_at": rfc3339(customer.created_at),
        "last_sign_in_at": rfc3339(customer.last_sign_in_at),
        "password_changed_at": rfc3339(customer.password_changed_at),
        "details_changed_at": rfc3339(customer.details_changed_at),
        "privacy_notice_version": customer.privacy_notice_version or None,
        "privacy_consent_at": rfc3339(customer.privacy_consent_at),
        "payments": visible_history(customer).count(),
        "active_sessions": CustomerSession.objects.filter(
            customer=customer, ended_at__isnull=True).count(),
    }


def update_details(session: CustomerSession, data, request=None) -> dict:
    """Correct the full name and/or email. The current password proves who is asking, even
    on a browser someone left signed in. An email change is told to both addresses."""
    data = _body_fields(data, ("current_password", "full_name", "email"))
    customer = session.customer
    current = data.get("current_password")
    if not isinstance(current, str) or not check_password(current[:256], customer.password):
        raise ApiError(400, "current_password_incorrect", "Your current password is not right.",
                       param="current_password")
    name = _clean_name(data["full_name"]) if "full_name" in data else customer.full_name
    email = _clean_email(data["email"]) if "email" in data else customer.email
    changed = [f for f, old, new in (("full_name", customer.full_name, name),
                                     ("email", customer.email, email)) if old != new]
    if not changed:
        return personal_data(customer)
    if "email" in changed and CustomerAccount.objects.filter(email__iexact=email).exclude(
            pk=customer.pk).exists():
        raise email_taken()
    old_email = customer.email
    try:
        with transaction.atomic():
            customer = CustomerAccount.objects.select_for_update().get(pk=customer.pk)
            customer.full_name, customer.email = name, email
            customer.details_changed_at = timezone.now()
            customer.save(update_fields=["full_name", "email", "details_changed_at"])
            _audit("customer.details_corrected", customer, request, fields=changed)
            if "email" in changed:
                # Reset links sent to the old address stop working.
                AccountToken.objects.filter(customer=customer, used_at__isnull=True).update(
                    used_at=timezone.now())
                for address in (old_email, email):
                    mail.notice(address, "your account email was changed",
                                f"Hello {customer.full_name},\n\nThe email address of your "
                                f"SecurePay account was changed from {old_email} to {email}."
                                "\n\nIf this was not you, reset your password straight away "
                                "and contact us.")
    except IntegrityError:
        raise email_taken() from None
    return personal_data(customer)


# --- password change and reset ---------------------------------------------------------

def _password_changed(customer: CustomerAccount, password: str,
                      keep: CustomerSession | None, request, action: str) -> int:
    """Inside a transaction: new hash, lockout cleared, other sessions ended (FR-ACC-08)."""
    customer = CustomerAccount.objects.select_for_update().get(pk=customer.pk)
    customer.password = make_password(password)
    customer.password_changed_at = timezone.now()
    customer.failed_attempts, customer.locked_until = 0, None
    customer.save(update_fields=["password", "password_changed_at", "failed_attempts",
                                 "locked_until"])
    AccountToken.objects.filter(customer=customer, purpose=RESET,
                                used_at__isnull=True).update(used_at=timezone.now())
    ended = end_sessions(customer, keep=keep)
    _audit(action, customer, request, sessions_ended=ended)
    mail.notice(customer.email, "your password was changed",
                f"Hello {customer.full_name},\n\nThe password of your SecurePay account was "
                "just changed, and you were signed out on every other device.\n\nIf this was "
                "not you, reset your password straight away.")
    return ended


def change_password(session: CustomerSession, data, request=None) -> int:
    """Signed in: current password + new one. This browser stays signed in."""
    data = _body_fields(data, ("current_password", "password"))
    customer = session.customer
    current = data.get("current_password")
    if not isinstance(current, str) or not check_password(current[:256], customer.password):
        raise ApiError(400, "current_password_incorrect", "Your current password is not right.",
                       param="current_password")
    password = _check_new_password(data.get("password"), customer)
    with transaction.atomic():
        return _password_changed(customer, password, session, request,
                                  "customer.password_changed")


def reset_requested_message() -> str:
    return ("If an account exists for this email, a reset link is on its way. The link works "
            f"once, for {_rules()['PASSWORD_RESET_LINK_TTL_MINUTES']} minutes.")


def reset_link(token: str) -> str:
    # The token goes in the fragment, so the browser never sends it to a server.
    return f"{settings.ACCOUNT_URL}/reset#token={token}"


def request_reset(data, request=None) -> str:
    """FR-ACC-07: the same reply whether or not the email is registered."""
    data = _body_fields(data, ("email",))
    email = data.get("email")
    if not isinstance(email, str) or not email.strip() or "@" not in email:
        raise invalid("missing_field", "Enter your email address.", param="email")
    account = CustomerAccount.objects.filter(email__iexact=email.strip()[:254],
                                             is_active=True).first()
    if account is None:
        return reset_requested_message()
    if tokens.recent_count(account, RESET, REQUEST_WINDOW_MINUTES) >= \
            _rules()["PASSWORD_RESET_REQUESTS_PER_ACCOUNT"]:
        return reset_requested_message()  # same reply, nothing sent
    minutes = _rules()["PASSWORD_RESET_LINK_TTL_MINUTES"]
    ttl = timedelta(minutes=minutes)
    with transaction.atomic():
        token = tokens.issue(account, RESET, ttl)
        mail.queue(
            OutboundEmail.Kind.PASSWORD_RESET, account.email, "reset your password",
            f"Hello {account.full_name},\n\nSomeone asked to reset the password of your "
            f"SecurePay account. To choose a new password, open this link within {minutes} "
            f"minutes:\n\n{reset_link(token)}\n\nThe link works once. If you did not ask for "
            "this, ignore this email; your password stays the same.",
            discard_after=timezone.now() + ttl)
        _audit("customer.password_reset_requested", account, request)
    return reset_requested_message()


def _reset_account(row: AccountToken) -> CustomerAccount:
    if row.customer_id is None or not row.customer.is_active:
        raise tokens.link_invalid()  # a staff link is no use here
    return row.customer


def check_reset_link(token) -> dict:
    account = _reset_account(tokens.peek(RESET, token))
    return {"email": account.email}


def reset_password(data, request=None) -> CustomerAccount:
    """FR-ACC-07, FR-ACC-08: uses the link up and ends every session of the account."""
    data = _body_fields(data, ("token", "password"))
    account = _reset_account(tokens.peek(RESET, data.get("token")))
    password = _check_new_password(data.get("password"), account)
    with transaction.atomic():
        row = tokens.consume(RESET, data.get("token"))  # a second use fails here
        account = _reset_account(row)
        _password_changed(account, password, None, request, "customer.password_reset")
    return account


def link_payment(payment: Payment, token: str | None) -> None:
    """Checkout: a payment submitted while signed in joins this customer's history. Called
    inside the submit transaction with the payment row locked."""
    session = current_session(token)
    if session is not None and payment.customer_id is None:
        payment.customer = session.customer
