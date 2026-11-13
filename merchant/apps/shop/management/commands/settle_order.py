"""Capture or cancel an order's SecurePay payment from the command line (demo story S1).

    python manage.py settle_order capture ORD-1001 [--amount 4000]
    python manage.py settle_order cancel ORD-1001

The same as the actions in the shop's admin. Retrying after a lost reply reuses the
attempt's saved Idempotency-Key, so the payment is never captured twice.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.shop import payments, securepay
from apps.shop.models import Order


class Command(BaseCommand):
    help = "Capture or cancel the SecurePay payment of an order."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["capture", "cancel"])
        parser.add_argument("order", help="Order reference, e.g. ORD-1001")
        parser.add_argument("--amount", type=int, default=None,
                            help="Capture less than the total (cents)")

    def handle(self, *args, action, order, amount, **options):
        try:
            number = int(order.removeprefix("ORD-"))
            found = Order.objects.get(pk=number - 1000)
        except (ValueError, Order.DoesNotExist):
            raise CommandError(f"No order {order}") from None
        attempt = found.attempts.exclude(payment_id="").order_by("-id").first()
        if attempt is None:
            raise CommandError(f"{order} has no SecurePay payment")
        try:
            if action == "capture":
                status = payments.capture(attempt, amount)
            else:
                status = payments.cancel(attempt)
        except (payments.SettleError, securepay.GatewayError) as exc:
            raise CommandError(f"SecurePay refused: {exc}") from None
        self.stdout.write(f"{found.reference} {attempt.payment_id}: {status}")
