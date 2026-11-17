"""Set up the Volt & Co. demo on a fresh stack: merchant, staff logins, block and review lists.

    python manage.py seed_demo --webhook-url https://shop.<domain>/webhooks/securepay

For the demo-day fallback laptop and for a brand-new server; `bash deploy/demo.sh seed` runs
it and puts the API key and signing secret into the shop's secrets. Safe to run again:
whatever already exists is left as it is (an existing merchant keeps its key, an existing
staff account keeps its password), so on the live server it only reports.

New staff accounts get a random temporary password, printed once; each person can set their
own with "Forgot your password?" and sets up the authenticator app at the first sign-in.

Nothing here invents payments: the dashboard shows only what really went through the
gateway (demo-day plan: synthetic history was dropped on purpose, it would be fake rows in an
audited system).
"""
import secrets
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import Role
from apps.merchants.demo import DEMO_MERCHANT_NAME, find_demo_merchant

# The same accounts as the README and RUNBOOK step 7, so the live server already has them.
DEMO_STAFF = [
    ("ops@demoshop.sg", Role.MERCHANT_OPERATOR, "Aisha Rahman"),
    ("analyst@securepay.sg", Role.FRAUD_ANALYST, "Daniel Lim"),
    ("admin@securepay.sg", Role.ADMINISTRATOR, "Mei Tan"),
]


def temporary_password() -> str:
    return f"{secrets.token_urlsafe(12)}-Sp1"


class Command(BaseCommand):
    help = "Create the Volt & Co. demo merchant, its staff logins and the risk lists if missing."

    def add_arguments(self, parser):
        parser.add_argument("--webhook-url", default="",
                            help="The shop's webhook URL, for a new merchant only.")
        parser.add_argument("--merchant", default="", help="Use this mer_ ID, not the name.")

    def handle(self, *args, webhook_url, merchant, **options):
        shop = find_demo_merchant(merchant)
        if shop is None and merchant:
            raise CommandError(f"No merchant {merchant}.")
        if shop is None:
            if not webhook_url:
                raise CommandError("A new demo merchant needs --webhook-url "
                                   "https://shop.<domain>/webhooks/securepay")
            call_command("create_merchant", DEMO_MERCHANT_NAME, webhook_url=webhook_url,
                         stdout=self.stdout)
            shop = find_demo_merchant()
        else:
            self.stdout.write(f"Merchant:       {shop.public_id} ({shop.name}) already exists; "
                              "its API key is unchanged.")

        User = get_user_model()
        for email, role, name in DEMO_STAFF:
            if User.objects.filter(username__iexact=email).exists():
                self.stdout.write(f"Staff {email} ({role}) already exists.")
                continue
            password = temporary_password()
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "password"
                path.write_text(password)
                call_command("create_staff", email, role=role.value, name=name,
                             merchant=shop.public_id if role == Role.MERCHANT_OPERATOR else None,
                             password_file=str(path), stdout=self.stdout)
            self.stdout.write(f"Temporary password for {email}: {password}")

        call_command("seed_risk_lists", stdout=self.stdout)
        self.stdout.write(f"Demo merchant ID: {shop.public_id}")
