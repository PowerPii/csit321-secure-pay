"""Get the gateway ready for a live demo and check it is healthy (demo-day checklist).

    python manage.py demo_check --merchant mer_...                       # checks only
    python manage.py demo_check --merchant mer_... --rename "Volt & Co."  # also rename
    python manage.py demo_check                                          # the merchant
                                                                         # named Volt & Co.

Run it on the server the morning of a demo and again an hour before. Each line says PASS,
WARN or FAIL; the command exits 1 if anything FAILs. It changes nothing except the optional
rename, which is audited like any other change. It never prints keys, secrets, emails or
card data.

The demo merchant was created as "Demo Shop"; since the demo-day polish the shop plays
Volt & Co., and the merchant name is what the payment page, receipts and dashboard show.
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.views import WORKER_STALE_AFTER_SECONDS
from apps.events.models import OutboundEmail, OutboxEvent, WorkerHeartbeat
from apps.merchants.demo import DEMO_MERCHANT_NAME, find_demo_merchant
from apps.merchants.models import Merchant
from apps.payments.models import Payment
from apps.payments.states import PaymentStatus
from apps.risk.scoring import ArtifactModel, active_model
from apps.security.models import MaintenanceRun, SecurityAlert


class Command(BaseCommand):
    help = "Check (and optionally rename) the demo merchant and the gateway before a demo."

    def add_arguments(self, parser):
        parser.add_argument("--merchant", default="",
                            help=f"The demo merchant's mer_ ID (default: the one named "
                                 f"{DEMO_MERCHANT_NAME!r}).")
        parser.add_argument("--rename", default="", help='New display name, e.g. "Volt & Co."')

    def handle(self, *args, merchant, rename, **options):
        shop = find_demo_merchant(merchant)
        if shop is None:
            raise CommandError(f"No merchant {merchant}." if merchant else
                               f"No merchant named {DEMO_MERCHANT_NAME!r}: pass --merchant "
                               "mer_... (and --rename) or run seed_demo.")
        rename = rename.strip()
        if rename and rename != shop.name:
            if len(rename) > 120:
                raise CommandError("The name can be at most 120 characters.")
            with transaction.atomic():
                old, shop.name = shop.name, rename
                shop.save(update_fields=["name", "updated_at"])
                audit("merchant.renamed", actor_type=AuditEvent.ActorType.SYSTEM,
                      actor_id="demo_check", merchant_id=shop.public_id,
                      target_type="merchant", target_id=shop.public_id,
                      details={"from": old, "to": rename})
            self.stdout.write(f"Renamed {shop.public_id} from {old!r} to {rename!r}.")

        results = list(self.checks(shop))
        for level, text in results:
            self.stdout.write(f"{level:<4}  {text}")
        failed = sum(level == "FAIL" for level, _ in results)
        warned = sum(level == "WARN" for level, _ in results)
        self.stdout.write(f"\n{len(results)} checks: {failed} failed, {warned} warnings.")
        if failed:
            raise SystemExit(1)

    def checks(self, shop: Merchant):
        now = timezone.now()
        day = now - timedelta(hours=24)

        yield (("PASS", f"Merchant {shop.name!r} is active") if shop.status == "active"
               else ("FAIL", f"Merchant {shop.name!r} is {shop.status}"))
        yield (("PASS", "Merchant has an active API key") if shop.api_keys.active().exists()
               else ("FAIL", "Merchant has no active API key"))
        if shop.webhook_url and shop.webhook_url_approved:
            yield ("PASS", "Webhook URL set and approved")
        else:
            yield ("FAIL", "Webhook URL missing or not approved: orders will not update")

        model = active_model()
        if isinstance(model, ArtifactModel):
            yield ("PASS", f"Fraud model {model.version} loaded")
        elif settings.RISK_MODEL_VERSION:
            yield ("FAIL", (f"Fraud model {settings.RISK_MODEL_VERSION} did not load: "
                            "screening blocks every payment"))
        else:
            yield ("WARN", "No fraud model configured: screening uses the stub")

        beat = WorkerHeartbeat.objects.filter(name="worker").first()
        if beat is None:
            yield ("FAIL", "The worker has never run: webhooks, emails and reconciliation stop")
        elif beat.seen_at < now - timedelta(seconds=WORKER_STALE_AFTER_SECONDS):
            yield ("FAIL", (f"The worker was last seen {beat.seen_at:%H:%M:%S} UTC: restart "
                            "gateway-worker"))
        else:
            yield ("PASS", "The worker is running")

        stuck = Payment.objects.filter(status=PaymentStatus.UNRESOLVED,
                                       updated_at__lt=now - timedelta(hours=1)).count()
        yield (("PASS", "No payment unresolved for over an hour") if not stuck
               else ("WARN", (f"{stuck} payment(s) unresolved for over an hour: is the "
                              "worker running?")))

        due = OutboundEmail.objects.filter(status=OutboundEmail.Status.PENDING,
                                           next_attempt_at__lt=now - timedelta(minutes=5)
                                           ).count()
        failed_mail = OutboundEmail.objects.filter(status__in=(OutboundEmail.Status.FAILED,
                                                               OutboundEmail.Status.BOUNCED),
                                                   created_at__gte=day).count()
        if due:
            yield ("FAIL", f"{due} email(s) overdue: the worker or the mail route is down")
        elif failed_mail:
            yield ("WARN", f"{failed_mail} email(s) failed or bounced in the last 24 hours")
        else:
            yield ("PASS", "Email outbox is flowing")

        late = OutboxEvent.objects.filter(status=OutboxEvent.Status.PENDING,
                                          merchant=shop,
                                          created_at__lt=now - timedelta(minutes=5)).count()
        yield (("PASS", "No webhooks waiting more than 5 minutes") if not late
               else ("WARN", f"{late} webhook(s) to the shop waiting over 5 minutes"))

        run = (MaintenanceRun.objects.filter(kind=MaintenanceRun.Kind.INTEGRITY)
               .order_by("-started_at").first())
        if run is None:
            yield ("WARN", "No integrity check has run yet")
        elif run.outcome != MaintenanceRun.Outcome.PASSED:
            yield ("FAIL", f"Last integrity check {run.outcome} ({run.public_id})")
        elif run.started_at < now - timedelta(hours=12):
            yield ("WARN", "Last integrity check is over 12 hours old")
        else:
            yield ("PASS", "Last integrity check passed")

        alerts = SecurityAlert.objects.filter(status=SecurityAlert.Status.OPEN).count()
        yield (("PASS", "No open security alerts") if not alerts
               else ("WARN", (f"{alerts} open security alert(s): review or close them "
                              "before the demo so the Security page starts clean")))
