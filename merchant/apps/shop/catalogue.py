"""Store rules of Volt & Co.: delivery fee and GST shown to the shopper.

Prices include GST, as Singapore retail prices do, so GST is shown but never added.
"""
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
