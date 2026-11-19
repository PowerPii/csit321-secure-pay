"""What a customer is told about a payment, in one place (completion audit, 19 Nov 2026).

The API's `status` values (PaymentStatus) never change; they are a contract with merchants.
These are only the words a customer reads, and every customer surface uses them: the guest
status page, the customer account history and payment detail (and, in the same words, the
hosted checkout and the demo shop). The full table, with the merchant and staff wording, is
docs/PAYMENT-LANGUAGE.md.

    Paid                              authorised, captured
    Not charged                       declined, blocked, cancelled, expired
    Being checked - do not pay again  unresolved (the bank's answer was lost; reconciliation decides)
    In progress                       created, screening, verification_required, processing
    Refunded / Partly refunded        a captured payment with completed refunds (history only)
"""
from apps.payments.states import PaymentStatus

PAID = frozenset({PaymentStatus.AUTHORISED, PaymentStatus.CAPTURED})
NOT_CHARGED = frozenset({PaymentStatus.DECLINED, PaymentStatus.BLOCKED,
                         PaymentStatus.CANCELLED, PaymentStatus.EXPIRED})

LABEL_PAID = "Paid"
LABEL_NOT_CHARGED = "Not charged"
LABEL_BEING_CHECKED = "Being checked - do not pay again"
LABEL_IN_PROGRESS = "In progress"


def customer_label(status: str, refunded: int = 0, captured: int = 0) -> str:
    """The customer's one-line status for a payment (guest-status.v1.yaml `status_label`)."""
    if refunded and captured:
        return "Refunded" if refunded >= captured else "Partly refunded"
    status = PaymentStatus(status)
    if status in PAID:
        return LABEL_PAID
    if status in NOT_CHARGED:
        return LABEL_NOT_CHARGED
    if status == PaymentStatus.UNRESOLVED:
        return LABEL_BEING_CHECKED
    return LABEL_IN_PROGRESS
