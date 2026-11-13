"""
Gateway worker: polls the outbox and job tables.

Run as its own container with `python manage.py run_worker`. Rows are claimed with
SELECT ... FOR UPDATE SKIP LOCKED, sent outside the transaction, and retried with
bounded backoff. The same loop runs reconciliation sweeps, verification expiry and
data purges.
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.payments import jobs

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the outbox / reconciliation / expiry worker loop."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=float, default=1.0, help="Seconds between polls")
        parser.add_argument("--once", action="store_true", help="Run one pass and exit")

    def handle(self, *args, interval, once, **options):
        self.stdout.write("worker started")
        while True:
            run_pass()
            if once:
                return
            time.sleep(interval)


def run_pass() -> None:
    """Run every job once. One job failing never stops the others or the loop."""
    close_old_connections()
    for job in JOBS:
        try:
            job()
        except Exception:
            logger.exception("Worker job %s failed", job.__name__)


def deliver_outbox():
    """Send due OutboxEvents as signed webhooks; back off; mark exhausted ones undelivered."""
    from apps.events.delivery import deliver_due

    deliver_due()


def reconcile_unresolved():
    """Query the simulator with the original operation ID at
    GATEWAY_RULES["RECONCILIATION_DELAYS_SECONDS"]; settle or escalate. Never sends a new
    charge. Also picks up operations a crashed process left without an answer (FR-TXN-15)."""
    from apps.payments.reconciliation import reconcile_due

    reconcile_due()


def expire_authorisations():
    """Cancel authorisations older than GATEWAY_RULES["AUTH_EXPIRY_DAYS"]."""
    jobs.expire_authorisations()


def expire_checkout_and_verification():
    """End checkout sessions past their hour: expired, or Blocked when a verification code
    was never entered (FR-CHK-21)."""
    jobs.expire_checkout_sessions()


def purge_card_data():
    """Delete vault card data for attempts that ended without submission."""
    from apps.vault.service import purge_expired

    purge_expired()


def purge_idempotency_records():
    """Free Idempotency-Keys past their 24 hours (contract section 5)."""
    from apps.payments.models import IdempotencyRecord

    IdempotencyRecord.purge_expired()


JOBS = [
    deliver_outbox,
    reconcile_unresolved,
    expire_authorisations,
    expire_checkout_and_verification,
    purge_card_data,
    purge_idempotency_records,
]
