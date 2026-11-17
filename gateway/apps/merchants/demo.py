"""The demo merchant (demo-day polish): the shop plays Volt & Co., a fictional gadget store.

`seed_demo` creates it on a fresh stack, `demo_check` finds it by name when no mer_ ID is
given. Every other merchant is left alone.
"""
from django.core.management.base import CommandError

from apps.merchants.models import Merchant

DEMO_MERCHANT_NAME = "Volt & Co."
# Created as "Demo Shop" before the reskin; `demo_check --rename` gives it the new name.
OLD_DEMO_MERCHANT_NAME = "Demo Shop"


def find_demo_merchant(public_id: str = "") -> Merchant | None:
    """The merchant with this ID, or else the only one named Volt & Co. (None if there is no
    such merchant). Two merchants with the demo name is an error: pass the ID instead."""
    if public_id:
        return Merchant.objects.filter(public_id=public_id).first()
    matches = list(Merchant.objects.filter(name=DEMO_MERCHANT_NAME)[:2])
    if len(matches) > 1:
        raise CommandError(f"More than one merchant is called {DEMO_MERCHANT_NAME!r}: "
                           "pass --merchant mer_...")
    return matches[0] if matches else None
