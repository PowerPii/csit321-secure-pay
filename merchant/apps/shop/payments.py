"""Starting and confirming SecurePay payments for orders."""
import logging
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.shop import securepay
from apps.shop.models import Order, PaymentAttempt

logger = logging.getLogger(__name__)
PAYMENT_ID = re.compile(r"^pay_[0-9A-Za-z]{24}$")


def return_url(order: Order) -> str:
    return f"{settings.SHOP_BASE_URL.rstrip('/')}/orders/{order.number}/return"


def start_payment(order: Order) -> PaymentAttempt:
    """Create (or retry creating) a SecurePay payment for the order.

    The attempt and its Idempotency-Key are saved first. If the reply is lost, the next try
    reuses the same key, so the gateway returns the payment it already made instead of a
    second one (API-CONTRACT.md section 5). Raises GatewayError if there is no usable reply.
    """
    attempt = order.attempts.filter(payment_id="").order_by("-id").first()
    if attempt is None:
        attempt = PaymentAttempt.objects.create(order=order)
    reply = securepay.create_payment(
        idempotency_key=str(attempt.idempotency_key), amount=order.total_cents,
        order_reference=order.reference, return_url=return_url(order),
        customer_email=order.email, description=order.description(),
        line_items=order.line_items())
    if reply.status != 201:
        error = reply.data.get("error", {})
        logger.error("SecurePay refused the payment for %s: %s", order.reference,
                     error.get("code"))
        raise securepay.GatewayError(error.get("code", f"HTTP {reply.status}"))
    apply_payment(attempt, reply.data, order)
    attempt.refresh_from_db()
    return attempt


def apply_payment(attempt: PaymentAttempt, data: dict, order: Order) -> bool:
    """Store a signed Payment snapshot if it is for this order and newer than what we have.

    Returns True if the order is paid. Checks the amount and order reference too, so a
    payment made for another order (or amount) can never pay this one.
    """
    if (data.get("object") != "payment" or data.get("order_reference") != order.reference
            or data.get("amount") != order.total_cents or data.get("currency") != "SGD"
            or not PAYMENT_ID.match(data.get("id") or "")):
        logger.error("SecurePay payment does not match order %s", order.reference)
        return False
    if attempt.payment_id and attempt.payment_id != data["id"]:
        return False
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        if data.get("sequence", 0) >= attempt.sequence:
            attempt.payment_id = data["id"]
            attempt.reference = data.get("reference") or ""
            attempt.status = data.get("status") or ""
            attempt.sequence = data.get("sequence", 0)
            # The API gives checkout_url only while the payment is "created". Keep the one we
            # have while a verification code is awaited, so the customer can get back to it.
            if data.get("checkout_url") or attempt.status != "verification_required":
                attempt.checkout_url = data.get("checkout_url") or ""
            attempt.captured_amount = data.get("captured_amount") or 0
            attempt.save()
        paid = attempt.status in PaymentAttempt.PAID
        if paid:
            Order.objects.filter(pk=order.pk, paid_at__isnull=True).update(
                paid_at=timezone.now())
    return paid


def refresh(attempt: PaymentAttempt) -> None:
    """Ask the gateway for the current, signed status (UC-28). Quietly keeps the old one
    if the gateway cannot be reached."""
    if not attempt.payment_id:
        return
    try:
        reply = securepay.get_payment(attempt.payment_id)
    except securepay.GatewayError:
        return
    if reply.status == 200:
        apply_payment(attempt, reply.data, attempt.order)


class SettleError(Exception):
    """The gateway refused a capture or cancel; the message is its error code."""


def capture(attempt: PaymentAttempt, amount: int | None = None) -> str:
    """Capture the order's payment (merchant back office, S1). Returns the new status.

    202 means SecurePay is still waiting for the processor; the webhook tells us later.
    """
    reply = securepay.capture_payment(attempt.payment_id,
                                      idempotency_key=str(attempt.capture_key), amount=amount)
    return _settled(attempt, reply)


def cancel(attempt: PaymentAttempt) -> str:
    reply = securepay.cancel_payment(attempt.payment_id, idempotency_key=str(attempt.cancel_key))
    return _settled(attempt, reply)


def _settled(attempt: PaymentAttempt, reply) -> str:
    if reply.status in (200, 202):
        apply_payment(attempt, reply.data, attempt.order)
        attempt.refresh_from_db()
        return attempt.status if reply.status == 200 else "pending"
    raise SettleError(reply.data.get("error", {}).get("code", f"HTTP {reply.status}"))


def refund(attempt: PaymentAttempt, amount: int, idempotency_key: str, reason: str = "") -> dict:
    """Refund part of the order's captured payment (demo story S6). Returns the Refund.

    Its status is completed, failed or unresolved; the refund.* webhook follows either way.
    """
    reply = securepay.refund_payment(attempt.payment_id, idempotency_key=idempotency_key,
                                     amount=amount, reason=reason)
    if reply.status != 201:
        raise SettleError(reply.data.get("error", {}).get("code", f"HTTP {reply.status}"))
    refresh(attempt)
    return reply.data
