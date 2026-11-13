"""Hosted checkout flow (UC-01, screens C3 to C7).

The checkout session ID in the URL is the only thing the browser holds. Merchant, amount
and currency come from the payment the merchant created and can never change here
(FR-CHK-03). Card details go straight to the vault; this module only sees the summary,
apart from handing the vault's one-time card to the simulator client on submit.
"""
import re
from email.utils import parseaddr
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.events.models import EventType
from apps.events.outbox import record_payment_event
from apps.payments import processor
from apps.payments.models import Operation, OutcomeReason, Payment
from apps.payments.processing import apply_authorise_answer
from apps.payments.states import PaymentStatus, check_transition
from apps.risk.pipeline import Outcome
from apps.risk.screening import screen_payment
from apps.vault import service as vault

SESSION_ID = re.compile(r"^cs_[0-9A-Za-z]{24}$")
CARD_FIELDS = {"number", "expiry_month", "expiry_year", "cvc", "email"}

# What the customer is told (C6, C7). Never a fraud reason (FR-MER-07 is for staff only).
RESULTS = {
    PaymentStatus.CREATED: "open",
    PaymentStatus.SCREENING: "processing",
    PaymentStatus.PROCESSING: "processing",
    PaymentStatus.VERIFICATION_REQUIRED: "verification_required",
    PaymentStatus.AUTHORISED: "approved",
    PaymentStatus.CAPTURED: "approved",
    PaymentStatus.DECLINED: "declined",
    PaymentStatus.BLOCKED: "not_completed",
    PaymentStatus.UNRESOLVED: "pending",
    PaymentStatus.CANCELLED: "cancelled",
    PaymentStatus.EXPIRED: "expired",
}


def _actor(payment):
    return {"actor_type": AuditEvent.ActorType.CUSTOMER, "actor_id": payment.checkout_session_id,
            "merchant_id": payment.merchant.public_id, "target_type": "payment",
            "target_id": payment.public_id}


def load(session_id: str) -> Payment:
    if not SESSION_ID.match(session_id or ""):
        raise not_found()
    payment = (Payment.objects.select_related("merchant")
               .filter(checkout_session_id=session_id).first())
    if payment is None:
        raise not_found()
    return expire_if_due(payment)


def expire_if_due(payment: Payment, request_id: str = "") -> Payment:
    """End a checkout session that passed its hour without a submission (payment.expired).

    The worker also does this on a schedule (apps.payments.jobs); doing it on access means the page
    never offers a session that has ended.
    """
    if payment.status != PaymentStatus.CREATED or timezone.now() < payment.checkout_expires_at:
        return payment
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("merchant").get(
            pk=payment.pk)
        if payment.status == PaymentStatus.CREATED and \
                timezone.now() >= payment.checkout_expires_at:
            check_transition(PaymentStatus.CREATED, PaymentStatus.EXPIRED)
            vault.discard(payment.card_token)
            payment.status = PaymentStatus.EXPIRED
            payment.outcome_reason = OutcomeReason.CHECKOUT_EXPIRED
            record_payment_event(payment, EventType.PAYMENT_EXPIRED)
            audit("payment.expired", **{**_actor(payment), "actor_type":
                                        AuditEvent.ActorType.SYSTEM, "actor_id": "checkout"},
                  request_id=request_id)
    return payment


def _session_closed(payment: Payment) -> ApiError:
    if payment.status == PaymentStatus.EXPIRED:
        return ApiError(410, "checkout_expired", "This checkout session has ended. Return to "
                        "the shop to start again.")
    return ApiError(409, "payment_already_submitted", "This payment was already submitted.")


def mask_email(email: str) -> str | None:
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    return f"{local[0]}•••@{domain}"


def return_url_for(payment: Payment) -> str:
    """`return_url?payment_id=pay_...` (API-CONTRACT.md section 3). Navigation only."""
    parts = urlsplit(payment.return_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k != "payment_id"]
    query.append(("payment_id", payment.public_id))
    return urlunsplit(parts._replace(query=urlencode(query)))


def to_dict(payment: Payment) -> dict:
    """What the hosted checkout page may know about its own payment."""
    status = PaymentStatus(payment.status)
    submitted = status not in (PaymentStatus.CREATED, PaymentStatus.EXPIRED)
    card = ({"brand": payment.card_brand, "last4": payment.card_last4}
            if payment.card_last4 else None)
    return {
        "session_id": payment.checkout_session_id,
        "status": status.value,
        "result": RESULTS[status],
        "merchant": {"name": payment.merchant.name},
        "amount": payment.amount,
        "currency": payment.currency,
        "order_reference": payment.order_reference,
        "description": payment.description or None,
        "line_items": payment.line_items or None,
        "reference": payment.reference if submitted else None,
        "email_required": not payment.customer_email,
        "customer_email_masked": mask_email(payment.customer_email),
        "card": card,
        "expires_at": rfc3339(payment.checkout_expires_at),
        "submitted_at": rfc3339(payment.submitted_at),
        "authorised_at": rfc3339(payment.authorised_at),
        "return_url": return_url_for(payment),
    }


def _clean_email(value) -> str:
    if not isinstance(value, str) or len(value) > 254 or parseaddr(value)[1] != value:
        raise invalid("invalid_email", "Enter a valid email address.", param="email")
    try:
        EmailValidator()(value)
    except ValidationError:
        raise invalid("invalid_email", "Enter a valid email address.", param="email") from None
    return value


def attach_card(payment: Payment, body: dict, request_id: str) -> Payment:
    """Card entry (C3): vault the card, keep only token, brand, last four and fingerprint."""
    if payment.status != PaymentStatus.CREATED:
        raise _session_closed(payment)
    for name in body:
        if name not in CARD_FIELDS:
            raise invalid("invalid_field", f"Unknown field '{name}'.", param=name)
    email = None
    if not payment.customer_email:
        email = _clean_email(body.get("email"))
    try:
        summary = vault.tokenise(body.get("number"), body.get("expiry_month"),
                                 body.get("expiry_year"), body.get("cvc"),
                                 expires_at=payment.checkout_expires_at)
    except vault.CardRejected as exc:
        raise invalid(exc.code, exc.message, param=exc.field) from None

    with transaction.atomic():
        locked = Payment.objects.select_for_update().select_related("merchant").get(
            pk=payment.pk)
        if locked.status != PaymentStatus.CREATED:
            vault.discard(summary.token)
            raise _session_closed(locked)
        previous = locked.card_token
        locked.card_token = summary.token
        locked.card_brand = summary.brand
        locked.card_last4 = summary.last4
        locked.card_fingerprint = summary.fingerprint
        if email:
            locked.customer_email = email
        locked.save()
        audit("checkout.card_added", **_actor(locked), request_id=request_id,
              details={"brand": summary.brand, "last4": summary.last4})
    vault.discard(previous)
    return locked


def submit(payment: Payment, request_id: str) -> Payment:
    """Pay (C3 -> C4): screen, record the operation, call the simulator, apply the answer.

    Submitting twice is harmless: the second call returns the payment as it is.
    """
    with transaction.atomic():
        payment = Payment.objects.select_for_update().select_related("merchant").get(
            pk=payment.pk)
        if payment.status == PaymentStatus.EXPIRED:
            raise _session_closed(payment)
        if payment.status != PaymentStatus.CREATED:
            return payment  # a double click or a reload; the first submission owns it
        if not payment.card_token:
            raise invalid("card_required", "Enter your card details first.")
        if not payment.customer_email:
            raise invalid("invalid_email", "Enter a valid email address.", param="email")
        card = vault.take(payment.card_token)  # deleted from the vault from here on
        if card is None:  # session ended or token purged: forget it and ask again
            payment.card_token = payment.card_brand = payment.card_last4 = ""  # nosec B105
            payment.card_fingerprint = ""
            payment.save()
        else:
            operation = _start_processing(payment, request_id)
    if card is None:
        raise invalid("card_required", "Please enter your card details again.")

    try:
        answer = processor.authorise(operation, payment, card)
    finally:
        del card
    return apply_authorise_answer(operation.pk, answer, request_id)


def _start_processing(payment: Payment, request_id: str) -> Operation:
    """created -> screening -> processing, and the operation row, in the caller's transaction."""
    check_transition(PaymentStatus.CREATED, PaymentStatus.SCREENING)
    payment.status = PaymentStatus.SCREENING
    payment.submitted_at = timezone.now()
    decision = screen_payment(payment)
    if decision.outcome is not Outcome.ALLOW:  # sprint 4 handles verify and block
        raise RuntimeError("only the stub Allow policy is wired in sprint 2")
    payment.screening_decision = decision.outcome.value
    check_transition(PaymentStatus.SCREENING, PaymentStatus.PROCESSING)
    payment.status = PaymentStatus.PROCESSING
    record_payment_event(payment, EventType.PAYMENT_PROCESSING)
    # Committed with the status change, before the call (SIMULATOR-CONTRACT.md 3.1).
    operation = Operation.objects.create(payment=payment, type=Operation.Type.AUTHORISE,
                                         amount=payment.amount)
    audit("payment.submitted", **_actor(payment), request_id=request_id,
          details={"screening": decision.outcome.value,
                   "policy_version": decision.policy_version,
                   "reasons": decision.reasons, "operation_id": operation.public_id})
    return operation
