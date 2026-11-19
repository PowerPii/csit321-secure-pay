"""Read-only customer payment history; every query is scoped to its owner."""
from apps.common.errors import not_found
from apps.customers.models import CustomerAccount
from apps.payments.labels import customer_label
from apps.payments.models import Payment
from apps.payments.states import PaymentStatus

# --- payment history (C11) -------------------------------------------------------------

# Payments still on the card form were never submitted by the customer.
HIDDEN = (PaymentStatus.CREATED, PaymentStatus.EXPIRED)


def visible_history(customer: CustomerAccount):
    return (Payment.objects.select_related("merchant").filter(customer=customer)
            .exclude(status__in=[s.value for s in HIDDEN]))


def _label(payment: Payment, refunded: int) -> str:
    # The same words as the guest status page and the receipt's status link (one vocabulary
    # for customers; completion audit, 19 Nov 2026). Blocked reads "Not charged": no
    # screening detail for customers.
    return customer_label(payment.status, refunded, payment.captured_amount)


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
