"""Create an approved merchant with an API key and signing secret, shown once.

    python manage.py create_merchant "Demo Shop" --webhook-url https://shop.localhost/webhooks/securepay

Stands in for the admin approval screen until it exists (MVP-SCOPE: admin creates and
approves merchants; self-registration comes later). Copy the key and secret into the
merchant service's secrets; they cannot be shown again.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.merchants.models import ApiKey, Merchant


class Command(BaseCommand):
    help = "Create an active merchant and print its API key and signing secret once."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--webhook-url", default="")
        parser.add_argument("--max-amount-cents", type=int, default=None)

    def handle(self, *args, name, webhook_url, max_amount_cents, **options):
        with transaction.atomic():
            merchant = Merchant(
                name=name,
                status=Merchant.Status.ACTIVE,
                webhook_url=webhook_url,
                webhook_url_approved=bool(webhook_url),
                max_amount_cents=max_amount_cents,
            )
            secret = merchant.rotate_signing_secret()
            merchant.save()
            api_key, plaintext = ApiKey.issue(merchant)
            for action, target_type, target_id in (
                ("merchant.created", "merchant", merchant.public_id),
                ("api_key.issued", "api_key", api_key.public_id),
            ):
                audit(action, actor_type=AuditEvent.ActorType.SYSTEM, actor_id="create_merchant",
                      merchant_id=merchant.public_id, target_type=target_type,
                      target_id=target_id)
        self.stdout.write(f"Merchant:       {merchant.public_id} ({merchant.name})")
        self.stdout.write(f"API key:        {plaintext}")
        self.stdout.write(f"Signing secret: {secret}")
        self.stdout.write("Store both now. They are not shown again.")
