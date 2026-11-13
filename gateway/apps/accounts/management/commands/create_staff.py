"""Create a staff account for the dashboard (stands in for D10 "Users and roles").

    python manage.py create_staff ops@demoshop.sg --role merchant_operator --merchant mer_...
    python manage.py create_staff analyst@securepay.sg --role fraud_analyst
    python manage.py create_staff admin@securepay.sg --role administrator

The password comes from --password-file, the STAFF_PASSWORD environment variable or a
prompt, and must pass the password rules (12 characters or more). The authenticator app is
set up at the first sign-in (D2 shows a QR code).
"""
import getpass
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.merchants.models import Merchant


class Command(BaseCommand):
    help = "Create a dashboard staff account (merchant operator, fraud analyst, administrator)."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--role", required=True, choices=[r.value for r in Role])
        parser.add_argument("--merchant", help="mer_... (merchant operators only)")
        parser.add_argument("--name", default="", help="Full name shown in the dashboard")
        parser.add_argument("--password-file")

    def handle(self, *args, email, role, merchant, name, password_file, **options):
        email = email.strip().lower()
        merchant_obj = None
        if role == Role.MERCHANT_OPERATOR:
            if not merchant:
                raise CommandError("A merchant operator needs --merchant mer_...")
            merchant_obj = Merchant.objects.filter(public_id=merchant).first()
            if merchant_obj is None:
                raise CommandError(f"No merchant {merchant}")
        elif merchant:
            raise CommandError("Only merchant operators belong to a merchant.")

        User = get_user_model()
        if User.objects.filter(username__iexact=email).exists():
            raise CommandError(f"{email} already exists.")
        if password_file:
            password = Path(password_file).read_text().strip()
        else:
            password = os.environ.get("STAFF_PASSWORD") or getpass.getpass("Password: ")
        first, _, last = name.partition(" ")
        user = User(username=email, email=email, first_name=first, last_name=last)
        try:
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from None
        with transaction.atomic():
            user.set_password(password)
            user.save()
            account = StaffAccount.objects.create(user=user, role=role, merchant=merchant_obj)
            audit("staff.created", actor_type=AuditEvent.ActorType.SYSTEM,
                  actor_id="create_staff", merchant_id=merchant or "", target_type="staff",
                  target_id=account.public_id, details={"role": role})
        self.stdout.write(f"Staff account {account.public_id}: {email} ({role})")
        self.stdout.write("Set up the authenticator app at the first sign-in.")
