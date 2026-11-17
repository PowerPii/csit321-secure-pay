"""Store rules of Volt & Co.: delivery fee, GST, stock levels and delivery dates.

Prices include GST, as Singapore retail prices do, so GST is shown but never added.
"""
import datetime

from django.utils import timezone

SHIPPING_SKU = "SHIP-STD"
SHIPPING_NAME = "Standard delivery"
SHIPPING_FEE_CENTS = 490
FREE_SHIPPING_FROM_CENTS = 8000
GST_RATE_PERCENT = 9


def shipping_cents(subtotal_cents: int) -> int:
    if subtotal_cents <= 0 or subtotal_cents >= FREE_SHIPPING_FROM_CENTS:
        return 0
    return SHIPPING_FEE_CENTS


def gst_included_cents(total_cents: int) -> int:
    """The GST inside a GST-inclusive total, rounded to the cent."""
    return round(total_cents * GST_RATE_PERCENT / (100 + GST_RATE_PERCENT))


# Stock shown on product cards: "Only 3 left" from this level down.
LOW_STOCK = 5
RESTOCK_TO = 25
DELIVERY_DAYS = (0, 1, 2, 3, 4, 5)  # Monday to Saturday, as the delivery page says
SAME_DAY_CUTOFF_HOUR = 14  # paid before 2 pm: ships today


def estimated_delivery(paid_at):
    """The day a paid order should arrive: next delivery day after it ships.

    Orders paid before 2 pm ship the same day; later ones ship the next day. Sundays have no
    delivery. Takes an aware datetime and works in the shop's time zone.
    """
    local = timezone.localtime(paid_at)
    day = local.date() + datetime.timedelta(days=0 if local.hour < SAME_DAY_CUTOFF_HOUR else 1)
    day += datetime.timedelta(days=1)
    while day.weekday() not in DELIVERY_DAYS:
        day += datetime.timedelta(days=1)
    return day
