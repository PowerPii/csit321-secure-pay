"""Read-only customer payment history; every query is scoped to its owner."""
from apps.common.errors import not_found
from apps.customers.models import CustomerAccount
from apps.payments.models import Payment
from apps.payments.states import PaymentStatus

# --- payment history (C11) -------------------------------------------------------------

# Payments still on the card form were never submitted by the customer.
HIDDEN = (PaymentStatus.CREATED, PaymentStatus.EXPIRED)
STATUS_LABELS = {
    PaymentStatus.SCREENING: "Processing",
    PaymentStatus.VERIFICATION_REQUIRED: "Awaiting code",
    PaymentStatus.PROCESSING: "Processing",
    PaymentStatus.AUTHORISED: "Authorised",
    PaymentStatus.CAPTURED: "Captured",
    PaymentStatus.DECLINED: "Declined",
    PaymentStatus.BLOCKED: "Declined",  # no screening detail for customers
    PaymentStatus.UNRESOLVED: "Being checked",
    PaymentStatus.CANCELLED: "Cancelled",
}


def visible_history(customer: CustomerAccount):
    return (Payment.objects.select_related("merchant").filter(customer=customer)
            .exclude(status__in=[s.value for s in HIDDEN]))


def _label(payment: Payment, refunded: int) -> str:
    if refunded and payment.captured_amount:
        return "Refunded" if refunded >= payment.captured_amount else "Partly refunded"
    return STATUS_LABELS.get(PaymentStatus(payment.status), "Processing")


def history(customer: CustomerAccount, limit: int = 100) -> dict:
    from apps.common.timefmt import rfc3339
    from apps.refunds.models import refund_totals

    rows = list(visible_history(customer).order_by("-created_at")[: limit + 1])
    items = []
    for payment in rows[:limit]:
        refunded = refund_totals(payment)[0] if payment.captured_amount else 0
        items.append({
            "reference": payment.reference,
            "merchant_name": payment.merchant.name,
            "amount": payment.amount,
            "currency": payment.currency,
            "status": payment.status,
            "status_label": _label(payment, refunded),
            "created_at": rfc3339(payment.created_at),
        })
    return {"data": items, "has_more": len(rows) > limit}


def own_payment(customer: CustomerAccount, reference) -> Payment:
    """One payment of this customer; anyone else's is 'not found', even with its reference."""
    from apps.guest.service import normalise_reference

    ref = normalise_reference(reference) if isinstance(reference, str) else None
    payment = visible_history(customer).filter(reference=ref).first() if ref else None
    if payment is None:
        raise not_found()
    return payment


def payment_detail(customer: CustomerAccount, reference) -> dict:
    from apps.guest.service import to_view

    payment = own_payment(customer, reference)
    view = to_view(payment)
    view["status_label"] = _label(payment, view.get("refunded_amount") or 0)
    view["order_reference"] = payment.order_reference
    return view
