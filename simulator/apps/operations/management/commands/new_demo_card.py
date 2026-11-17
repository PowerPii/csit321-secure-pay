"""Print fresh demo card numbers with no screening history.

    python manage.py new_demo_card                         # one Visa that approves
    python manage.py new_demo_card --count 3 --mastercard
    python manage.py new_demo_card --kind lost-response     # S4: the bank never answers
    python manage.py new_demo_card --set                    # one card per demo scene

Synthetic numbers in reserved demo ranges (SIMULATOR-CONTRACT.md section 5); never real.
`--set` prints the cards for the demo script with the scene each one is for; the team keeps
4242 4242 4242 4242 and the other fixed cards for testing.
"""
from django.core.management.base import BaseCommand

from apps.operations.test_cards import DEMO_KINDS, new_demo_card

# (scene, kind). The blocked card and the high-amount rule are gateway-side and stay fixed.
DEMO_SET = [
    ("S1  Mei buys a cable (approves)", "approve"),
    ("S2  Mei buys a laptop (approves after the code)", "approve-mastercard"),
    ("S3  Card testing: pay 6 times quickly, the 6th is blocked", "approve"),
    ("S4  The bank goes quiet (lost response, reconciled)", "lost-response"),
    ("--  Spare: declined, insufficient funds", "decline"),
    ("--  Spare: approves", "approve"),
]


def spaced(number: str) -> str:
    return " ".join(number[i:i + 4] for i in range(0, 16, 4))


class Command(BaseCommand):
    help = "Print fresh demo card numbers (no screening history yet)."

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=1)
        parser.add_argument("--mastercard", action="store_true",
                            help="Same as --kind approve-mastercard.")
        parser.add_argument("--kind", choices=sorted(DEMO_KINDS), default="approve")
        parser.add_argument("--set", dest="scene_set", action="store_true",
                            help="One fresh card per demo scene, with what it is for.")

    def handle(self, *args, count, mastercard, kind, scene_set, **options):
        if scene_set:
            for scene, scene_kind in DEMO_SET:
                self.stdout.write(f"{spaced(new_demo_card(DEMO_KINDS[scene_kind]))}  {scene}")
            self.stdout.write("Any future expiry (e.g. 12/30) and any 3-digit code. "
                              "S3 blocked-list card: 4000 0000 0000 0101.")
            return
        prefix = DEMO_KINDS["approve-mastercard" if mastercard else kind]
        for _ in range(max(1, min(count, 20))):
            self.stdout.write(spaced(new_demo_card(prefix)))
