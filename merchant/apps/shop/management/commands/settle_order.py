"""Capture, cancel or refund an order's SecurePay payment from the command line (S1, S6).

    python manage.py settle_order capture ORD-1001 [--amount 4000]
    python manage.py settle_order cancel ORD-1001
    python manage.py settle_order refund ORD-1001 --amount 1500 [--reason "..."] [--key K]

The same as the actions in the shop's admin. Retrying after a lost reply reuses the
attempt's saved Idempotency-Key, so the payment is never captured twice. Each refund gets a
new key, printed so a refund whose reply was lost can be retried with `--key`.
"""
import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.shop import payments, securepay
from apps.shop.models import Order


class Command(BaseCommand):
    help = "Capture, cancel or refund the SecurePay payment of an order."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["capture", "cancel", "refund"])
        parser.add_argument("order", help="Order reference, e.g. ORD-1001")
        parser.add_argument("--amount", type=int, default=None,
                            help="Capture less than the total, or the refund amount (cents)")
        parser.add_argument("--reason", default="", help="Refund reason (free text)")
        parser.add_argument("--key", default=None,
                            help="Idempotency-Key, to retry a refund whose reply was lost")

    def handle(self, *args, action, order, amount, reason, key, **options):
        try:
            number = int(order.removeprefix("ORD-"))
            found = Order.objects.get(pk=number - 1000)
        except (ValueError, Order.DoesNotExist):
            raise CommandError(f"No order {order}") from None
        attempt = found.attempts.exclude(payment_id="").order_by("-id").first()
        if attempt is None:
            raise CommandError(f"{order} has no SecurePay payment")
        if action == "refund":
            if not amount:
                raise CommandError("A refund needs --amount (cents)")
            key = key or str(uuid.uuid4())
            try:
                data = payments.refund(attempt, amount, key, reason)
            except (payments.SettleError, securepay.GatewayError) as exc:
                raise CommandError(f"SecurePay refused: {exc} (Idempotency-Key {key})") from None
            self.stdout.write(f"{found.reference} {attempt.payment_id}: refund {data['reference']} "
                              f"{data['amount']} {data['status']} (Idempotency-Key {key})")
            return
        try:
            if action == "capture":
                status = payments.capture(attempt, amount)
            else:
                status = payments.cancel(attempt)
        except (payments.SettleError, securepay.GatewayError) as exc:
            raise CommandError(f"SecurePay refused: {exc}") from None
        self.stdout.write(f"{found.reference} {attempt.payment_id}: {status}")
