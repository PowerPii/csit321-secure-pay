"""
Gateway worker: polls the outbox and job tables.

Run as its own container with `python manage.py run_worker`. Rows are claimed with
SELECT ... FOR UPDATE SKIP LOCKED, sent outside the transaction, and retried with
bounded backoff. The same loop runs reconciliation sweeps, verification expiry and
data purges.
"""
import time

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Run the outbox / reconciliation / expiry worker loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=1.0, help="Seconds between polls")
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args, interval, once, **options):
        self.stdout.write("worker started")
        while True:
            self.run_pass()
            if once:
                return
            time.sleep(interval)

    def run_pass(self):
        for job in JOBS:
            job()


# Each job claims its own rows with SELECT ... FOR UPDATE SKIP LOCKED, so several
# workers can run safely. Fill these in as the models land (see docs/MVP-SCOPE.md).
def deliver_outbox():
    """Send due OutboxEvents as signed webhooks; back off; mark exhausted ones for staff."""


def reconcile_unresolved():
    """Query the simulator with the original operation ID; settle or escalate after
    GATEWAY_RULES["RECONCILIATION_MAX_CHECKS"]. Never sends a new charge."""


def expire_authorisations():
    """Cancel authorisations older than GATEWAY_RULES["AUTH_EXPIRY_DAYS"]."""


def expire_checkout_and_verification():
    """End checkout sessions and verification codes past their TTL (payment -> Expired/Blocked)."""


def purge_card_data():
    """Delete vault card data for attempts that ended without submission."""


JOBS = [
    deliver_outbox,
    reconcile_unresolved,
    expire_authorisations,
    expire_checkout_and_verification,
    purge_card_data,
]
