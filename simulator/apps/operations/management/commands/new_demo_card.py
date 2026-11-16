"""Print fresh demo card numbers that approve and have no screening history.

    python manage.py new_demo_card            # one Visa
    python manage.py new_demo_card --count 3 --mastercard

Synthetic numbers in a reserved test range (SIMULATOR-CONTRACT.md section 5); never real.
"""
from django.core.management.base import BaseCommand

from apps.operations.test_cards import DEMO_APPROVE_PREFIXES, new_demo_card


class Command(BaseCommand):
    help = "Print fresh approve-range demo card numbers (no screening history yet)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=1)
        parser.add_argument("--mastercard", action="store_true")

    def handle(self, *args, count, mastercard, **options):
        prefix = DEMO_APPROVE_PREFIXES[1 if mastercard else 0]
        for _ in range(max(1, min(count, 20))):
            number = new_demo_card(prefix)
            self.stdout.write(" ".join(number[i:i + 4] for i in range(0, 16, 4)))
