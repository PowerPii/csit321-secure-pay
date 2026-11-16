"""Seed the block and review lists for the demo (MVP-SCOPE: "seeds the blocklist").

    python manage.py seed_risk_lists

Safe to run on every start: missing entries are created and nothing is duplicated. An entry an
administrator removed from the block list stays removed (FR-FRD-09).
"""
from django.core.management.base import BaseCommand

from apps.risk import hashing
from apps.risk.models import RiskListEntry
from apps.vault.demo_cards import demo_card_fingerprint

Kind, Action = RiskListEntry.Kind, RiskListEntry.Action

SEED = [
    (Kind.CARD, lambda: demo_card_fingerprint("blocklisted"), Action.BLOCK,
     "Demo: test card 4000 0000 0000 0101 reported stolen"),
    (Kind.EMAIL, lambda: hashing.email_hash("blocked@example.com"), Action.BLOCK,
     "Demo: blocked@example.com linked to earlier fraud"),
    (Kind.EMAIL, lambda: hashing.email_hash("review@example.com"), Action.VERIFY,
     "Demo: review@example.com needs verification"),
]


class Command(BaseCommand):
    help = "Create or update the demo block and review list entries."

    def handle(self, *args, **options):
        for kind, value, action, label in SEED:
            RiskListEntry.objects.get_or_create(
                kind=kind, value_hash=value(),
                defaults={"action": action, "label": label, "active": True,
                          "display": label[:60]})
        self.stdout.write(f"{len(SEED)} risk list entries in place.")
