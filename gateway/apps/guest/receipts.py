"""Emailed receipts: an authorised payment (FR-CHK-15, UC-04) and a completed refund.

Amount, merchant, date, card brand and last four digits, and the payment reference; for a
guest payment (every payment in the MVP) a link to the guest status page that fills in the
reference. Queued in the same transaction as the authorisation, sent by the worker.

A refund receipt (demo sprint 14) is queued in the transaction that marks the refund
completed, so the customer hears about money coming back only once the simulator has
confirmed it, and only once even if a late answer arrives.
"""
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from django.conf import settings

from apps.events.emails import queue
from apps.events.models import OutboundEmail

BRANDS = {"visa": "Visa", "mastercard": "Mastercard"}


def money(cents: int) -> str:
    return f"S${cents / 100:,.2f}"


def status_link(reference: str) -> str:
    return f"{settings.GUEST_STATUS_URL}?{urlencode({'ref': reference})}"


def body_for(payment) -> str:
    when = payment.authorised_at.astimezone(ZoneInfo(settings.DASHBOARD_TIME_ZONE))
    card = (f"{BRANDS.get(payment.card_brand, payment.card_brand.title() or 'Card')} "
            f"ending {payment.card_last4}" if payment.card_last4 else "Card")
    lines = [
        f"Thank you. Your payment to {payment.merchant.name} was approved.",
        "",
        f"Amount:     {money(payment.amount)}",
        f"Paid to:    {payment.merchant.name}",
        f"Date:       {when:%d %b %Y, %H:%M} (Singapore time)",
        f"Card:       {card}",
        f"Reference:  {payment.reference}",
    ]
    if payment.line_items:
        lines += ["", "Items:"]
        lines += [f"  {item['name']} x {item['quantity']}  "
                  f"{money(item['unit_amount'] * item['quantity'])}"
                  for item in payment.line_items]
        lines += [f"  Total  {money(payment.amount)}"]
    lines += [
        "",
        "Keep the reference for any question about this payment.",
        "",
        ("Check this payment later (you will need the email address you paid with, and we "
         "will email you a one-time code):"),
        status_link(payment.reference),
        "",
        ("SecurePay processes payments for the shop. We never ask for your card details or "
         "a code by phone or message."),
    ]
    return "\n".join(lines) + "\n"


def queue_receipt(payment) -> OutboundEmail | None:
    """Call inside the authorisation's transaction. No email address, no receipt."""
    if not payment.customer_email:
        return None
    subject = (f"Receipt: {money(payment.amount)} to {payment.merchant.name} "
               f"({payment.reference})")
    return queue(OutboundEmail.Kind.RECEIPT, payment, payment.customer_email, subject,
                 body_for(payment))


def refund_body_for(refund) -> str:
    payment = refund.payment
    when = refund.completed_at.astimezone(ZoneInfo(settings.DASHBOARD_TIME_ZONE))
    card = (f"{BRANDS.get(payment.card_brand, payment.card_brand.title() or 'Card')} "
            f"ending {payment.card_last4}" if payment.card_last4 else "The card you paid with")
    full = refund.amount == payment.amount
    lines = [
        f"{payment.merchant.name} refunded {money(refund.amount)} to your card.",
        "",
        f"Refund:      {money(refund.amount)}{' (full refund)' if full else ''}",
        f"From:        {payment.merchant.name}",
        f"Date:        {when:%d %b %Y, %H:%M} (Singapore time)",
        f"Card:        {card}",
        f"Refund ref:  {refund.reference}",
        f"Payment:     {payment.reference} ({money(payment.amount)})",
        "",
        ("Your bank usually shows a refund within 5 to 10 working days. This is a simulated "
         "payment, so no real money moves."),
        "",
        ("Check the payment later (you will need the email address you paid with, and we "
         "will email you a one-time code):"),
        status_link(payment.reference),
        "",
        ("Questions about the order itself go to the shop. SecurePay never asks for your "
         "card details or a code by phone or message."),
    ]
    return "\n".join(lines) + "\n"


def queue_refund_receipt(refund) -> OutboundEmail | None:
    """Call inside the transaction that completes the refund."""
    payment = refund.payment
    if not payment.customer_email:
        return None
    subject = (f"Refund: {money(refund.amount)} from {payment.merchant.name} "
               f"({payment.reference})")
    return queue(OutboundEmail.Kind.REFUND_RECEIPT, payment, payment.customer_email, subject,
                 refund_body_for(refund))
