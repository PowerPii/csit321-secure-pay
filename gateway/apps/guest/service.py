"""Guest status check (API-CONTRACT.md section 8; openapi/guest-status.v1.yaml).

Same reply whether or not the reference and email match (FR-ACC-06): a request that
matches nothing still creates a challenge, still counts towards the request limits, and
the email (if any) leaves through the outbox, so nothing in the reply or its timing tells
the two apart. Every limit comes from GATEWAY_RULES["GUEST_STATUS_*"].
"""
import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.common.errors import ApiError, invalid
from apps.common.timefmt import rfc3339
from apps.events.emails import queue
from apps.events.models import EventType, OutboundEmail, OutboxEvent
from apps.guest.models import StatusChallenge, StatusLock, StatusSession
from apps.payments.models import Payment
from apps.payments.states import PaymentStatus
from apps.refunds.models import refund_totals

RULES = settings.GATEWAY_RULES
WINDOW = timedelta(minutes=15)  # the request limits count over this window (contract step 5)
MESSAGE = ("If the details match a payment, we have emailed a 6-digit code to that address. "
           "It is valid for 10 minutes.")
COOKIE = "sp_guest_status"
COOKIE_PATH = "/guest/status"
REFERENCE_CHARS = re.compile(r"[^0-9A-Za-z]")


def _key(purpose: str, value: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), f"guest:{purpose}:{value}".encode(),
                    hashlib.sha256).hexdigest()


def normalise_reference(raw: str) -> str | None:
    """'sp 7kq4-m2xd' -> 'SP-7KQ4-M2XD'. Case, spaces and dashes are ignored."""
    chars = REFERENCE_CHARS.sub("", raw).upper()
    if len(chars) != 10 or not chars.startswith("SP"):
        return None
    return f"SP-{chars[2:6]}-{chars[6:]}"


def pair_key(reference: str, email: str) -> str:
    return _key("pair", f"{reference}|{email.strip().lower()}")


def _code_hash(challenge_id: str, code: str) -> str:
    return _key("code", f"{challenge_id}:{code}")


def _retry_after(until) -> int:
    return max(1, int((until - timezone.now()).total_seconds()) + 1)


def _rate_limited(oldest_in_window) -> ApiError:
    return ApiError(429, "rate_limited", "Too many code requests. Try again later.",
                    retry_after=_retry_after(oldest_in_window + WINDOW))


def parse_code_request(data: dict) -> tuple[str | None, str]:
    for name in ("reference", "email"):
        if name not in data:
            raise invalid("missing_field", f"'{name}' is required.", name)
    for name in data:
        if name not in ("reference", "email"):
            raise invalid("invalid_field", f"Unknown field '{name}'.", name)
    reference, email = data["reference"], data["email"]
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 32:
        raise invalid("invalid_field", "Enter the payment reference from your receipt.",
                      "reference")
    if not isinstance(email, str) or len(email) > 254:
        raise invalid("invalid_field", "Enter the email address you paid with.", "email")
    try:
        validate_email(email.strip())
    except ValidationError:
        raise invalid("invalid_field", "Enter the email address you paid with.",
                      "email") from None
    # A malformed reference is answered like a non-matching one (no hint either way).
    return normalise_reference(reference), email.strip()


def request_code(data: dict, ip: str | None) -> dict:
    reference, email = parse_code_request(data)
    pair = pair_key(reference or REFERENCE_CHARS.sub("", data["reference"]).upper(), email)
    ip_key = _key("ip", ip or "unknown")
    now = timezone.now()
    since = now - WINDOW
    with transaction.atomic():
        # Serialise requests for one pair, so the limit cannot be raced.
        lock, _ = StatusLock.objects.select_for_update().get_or_create(pair_key=pair)
        recent_pair = StatusChallenge.objects.filter(pair_key=pair, created_at__gte=since)
        if recent_pair.count() >= RULES["GUEST_STATUS_CODE_REQUESTS_PER_PAIR"]:
            raise _rate_limited(recent_pair.order_by("created_at").first().created_at)
        recent_ip = StatusChallenge.objects.filter(ip_key=ip_key, created_at__gte=since)
        if recent_ip.count() >= RULES["GUEST_STATUS_CODE_REQUESTS_PER_IP"]:
            raise _rate_limited(recent_ip.order_by("created_at").first().created_at)

        payment = None
        if reference is not None:
            payment = (Payment.objects.select_related("merchant")
                       .filter(reference=reference, customer_email__iexact=email)
                       .exclude(customer_email="").first())
        StatusChallenge.objects.filter(pair_key=pair, replaced_at__isnull=True,
                                       used_at__isnull=True).update(replaced_at=now)
        code = f"{secrets.randbelow(1_000_000):06d}"
        ttl = timedelta(minutes=RULES["GUEST_STATUS_CODE_TTL_MINUTES"])
        challenge = StatusChallenge(pair_key=pair, ip_key=ip_key, payment=payment,
                                    code_hash="", expires_at=now + ttl)
        challenge.save()
        challenge.code_hash = _code_hash(challenge.public_id, code)
        challenge.save(update_fields=["code_hash"])
        locked = lock.locked_until is not None and lock.locked_until > now
        if payment is not None and not locked:
            queue(OutboundEmail.Kind.GUEST_STATUS_CODE, payment, payment.customer_email,
                  f"{code} is your SecurePay status code",
                  _code_email(payment, code), discard_after=challenge.expires_at)
    return {"challenge_id": challenge.public_id, "message": MESSAGE,
            "expires_in_seconds": int(ttl.total_seconds())}


def _code_email(payment: Payment, code: str) -> str:
    minutes = RULES["GUEST_STATUS_CODE_TTL_MINUTES"]
    return (
        f"Your SecurePay status code is {code}\n\n"
        f"Enter it on the payment status page to see payment {payment.reference} to "
        f"{payment.merchant.name}. It expires in {minutes} minutes and works once.\n\n"
        "If you did not ask for this code, ignore this email; nobody can see the payment "
        "without it.\nSecurePay will never ask you for this code by phone or message.\n"
    )


def _code_error(code: str, message: str, remaining: int) -> ApiError:
    return ApiError(400, code, message, "code", extra={"attempts_remaining": remaining})


def verify_code(data: dict) -> tuple[Payment, str]:
    """Check the code; on success return the payment and a new session token."""
    for name in ("challenge_id", "code"):
        if name not in data:
            raise invalid("missing_field", f"'{name}' is required.", name)
    challenge_id, code = data["challenge_id"], data["code"]
    if not isinstance(challenge_id, str) or not re.fullmatch(r"gsc_[0-9A-Za-z]{24}",
                                                             challenge_id):
        raise invalid("invalid_field", "Ask for a new code.", "challenge_id")
    if not isinstance(code, str) or not re.fullmatch(r"[0-9]{6}", code):
        raise invalid("invalid_field", "Enter the 6-digit code from the email.", "code")
    max_attempts = RULES["GUEST_STATUS_MAX_ATTEMPTS"]
    now = timezone.now()
    error = None
    with transaction.atomic():
        challenge = (StatusChallenge.objects.select_for_update()
                     .filter(public_id=challenge_id).first())
        if challenge is None:
            raise _code_error("code_expired", "This code has expired. Ask for a new one.",
                              max_attempts)
        lock, _ = StatusLock.objects.select_for_update().get_or_create(
            pair_key=challenge.pair_key)
        if lock.locked_until is not None and lock.locked_until > now:
            raise _locked(lock.locked_until)
        if challenge.used_at or challenge.replaced_at or now >= challenge.expires_at:
            raise _code_error("code_expired", "This code has expired. Ask for a new one.",
                              max(0, max_attempts - lock.wrong_attempts))
        correct = challenge.payment_id is not None and hmac.compare_digest(
            challenge.code_hash, _code_hash(challenge.public_id, code))
        if correct:
            challenge.used_at = now
            challenge.save(update_fields=["used_at"])
            lock.wrong_attempts, lock.locked_until = 0, None
            lock.save()
            token = secrets.token_urlsafe(32)
            StatusSession.objects.create(
                token_hash=_key("session", token), payment_id=challenge.payment_id,
                expires_at=now + timedelta(minutes=RULES["GUEST_STATUS_SESSION_MINUTES"]))
        else:
            # Wrong codes count across codes for the pair; the third locks it (FR-ACC-06).
            lock.wrong_attempts += 1
            if lock.wrong_attempts >= max_attempts:
                lock.wrong_attempts = 0
                lock.locked_until = now + timedelta(minutes=RULES["GUEST_STATUS_LOCK_MINUTES"])
                challenge.replaced_at = now
                challenge.save(update_fields=["replaced_at"])
                error = _locked(lock.locked_until)
            else:
                left = max_attempts - lock.wrong_attempts
                error = _code_error("code_incorrect",
                                    f"That code is not right. You have {left} "
                                    f"{'try' if left == 1 else 'tries'} left.", left)
            lock.save()
    if error is not None:
        raise error  # after the commit, so the wrong attempt stays counted
    return Payment.objects.select_related("merchant").get(pk=challenge.payment_id), token


def _locked(until) -> ApiError:
    local = until.astimezone(ZoneInfo(settings.DASHBOARD_TIME_ZONE))
    return ApiError(429, "status_check_locked",
                    "Too many wrong codes. The status check for this payment is locked for "
                    f"{RULES['GUEST_STATUS_LOCK_MINUTES']} minutes. Try again after "
                    f"{local:%H:%M}, or contact the shop for help with your order.",
                    retry_after=_retry_after(until))


def session_payment(token: str | None) -> Payment:
    if not token:
        raise ApiError(401, "status_session_missing",
                       "Enter your payment details to see its status.")
    session = (StatusSession.objects.select_related("payment__merchant")
               .filter(token_hash=_key("session", token)).first())
    if session is None or session.ended_at is not None:
        raise ApiError(401, "status_session_missing",
                       "Enter your payment details to see its status.")
    if timezone.now() >= session.expires_at:
        raise ApiError(401, "status_session_expired",
                       "This view has timed out. Ask for a new code to see the payment again.")
    return session.payment


def end_session(token: str | None) -> None:
    if token:
        StatusSession.objects.filter(token_hash=_key("session", token),
                                     ended_at__isnull=True).update(ended_at=timezone.now())


# --- the read-only view (GuestPaymentView) -----------------------------------------------

PAID = {PaymentStatus.AUTHORISED, PaymentStatus.CAPTURED}
NOT_CHARGED = {PaymentStatus.DECLINED, PaymentStatus.BLOCKED, PaymentStatus.CANCELLED,
               PaymentStatus.EXPIRED}
EVENT_LABELS = {
    EventType.PAYMENT_VERIFICATION_REQUIRED: "Checked",
    EventType.PAYMENT_PROCESSING: "Checked",
    EventType.PAYMENT_AUTHORISED: "Approved by the bank",
    EventType.PAYMENT_DECLINED: "Not charged",
    EventType.PAYMENT_BLOCKED: "Not charged",
    EventType.PAYMENT_UNRESOLVED: "Being checked with the bank",
    EventType.PAYMENT_CAPTURED: "Charged",
    EventType.PAYMENT_CANCELLED: "Cancelled, not charged",
    EventType.PAYMENT_EXPIRED: "Cancelled, not charged",
}


def status_label(status: str) -> str:
    status = PaymentStatus(status)
    if status in PAID:
        return "Paid"
    if status in NOT_CHARGED:
        return "Not charged"
    if status == PaymentStatus.UNRESOLVED:
        return "Being checked - do not pay again"
    return "In progress"


def _money(cents: int) -> str:
    return f"S${cents / 100:,.2f}"


def timeline(payment: Payment) -> list[dict]:
    """Customer-visible changes, oldest first: no reasons, no screening detail."""
    items = [{"at": rfc3339(payment.created_at), "label": "Payment started"}]
    events = (OutboxEvent.objects.filter(payment=payment).order_by("sequence")
              .values_list("type", "created_at", "payload"))
    for event_type, at, payload in events:
        if event_type == EventType.REFUND_COMPLETED:
            amount = ((payload.get("data") or {}).get("object") or {}).get("amount")
            label = f"Refunded {_money(amount)}" if amount else "Refunded"
        else:
            label = EVENT_LABELS.get(event_type)
        if label is None or items[-1]["label"] == label:
            continue
        items.append({"at": rfc3339(at), "label": label})
    return items


def to_view(payment: Payment) -> dict:
    refunded = refund_totals(payment)[0] if payment.captured_amount else 0
    return {
        "reference": payment.reference,
        "merchant_name": payment.merchant.name,
        "amount": payment.amount,
        "currency": payment.currency,
        "status": payment.status,
        "status_label": status_label(payment.status),
        "card": ({"brand": payment.card_brand or "card", "last4": payment.card_last4}
                 if payment.card_last4 else None),
        "refunded_amount": refunded,
        "created_at": rfc3339(payment.created_at),
        "timeline": timeline(payment),
    }
