"""The daily personal data clean-up (NFR-PRI-01).

    run(started_by="", now=None) -> MaintenanceRun

Personal data older than RETENTION_DAYS (365: the URS's 12-month project assumption) is
deleted or anonymised:

  payments            customer email removed and the customer account unlinked; amounts,
                      status, card brand and last 4 digits stay for the merchant's records
  screening records   the keyed email and IP hashes removed (the card fingerprint stays,
                      it is not personal data on its own)
  queued emails       deleted (the body holds the customer's address and payment details)
  guest status codes  challenges, locks and sessions deleted
  account tokens      used or expired reset and verification links deleted
  customer sessions   ended or expired sessions deleted

Audit entries are append-only and are not touched: they never hold email addresses or
phone numbers (`apps.audit.models.record` masks them) and refer to people by ID only.
Customer accounts are kept while the customer uses them; their own data is shown to them.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.security.models import MaintenanceRun


def cutoff(now=None):
    return (now or timezone.now()) - timedelta(days=settings.GATEWAY_RULES["RETENTION_DAYS"])


def run(started_by: str = "", now=None) -> MaintenanceRun:
    from apps.accounts.models import AccountToken
    from apps.customers.models import CustomerSession
    from apps.events.models import OutboundEmail
    from apps.guest.models import StatusChallenge, StatusLock, StatusSession
    from apps.payments.models import Payment
    from apps.risk.models import ScreeningEvent

    started = timezone.now()
    before = cutoff(now)
    with transaction.atomic():
        counts = {
            "payments_anonymised": Payment.objects.filter(created_at__lt=before)
            .exclude(customer_email="", customer__isnull=True)
            .update(customer_email="", customer=None),
            "screening_records_anonymised": ScreeningEvent.objects
            .filter(occurred_at__lt=before).exclude(email_hash="", ip_hash="")
            .update(email_hash="", ip_hash=""),
            "emails_deleted": OutboundEmail.objects.filter(created_at__lt=before).delete()[0],
            "guest_status_records_deleted": (
                StatusSession.objects.filter(created_at__lt=before).delete()[0]
                + StatusChallenge.objects.filter(created_at__lt=before).delete()[0]
                + StatusLock.objects.filter(updated_at__lt=before).delete()[0]),
            "account_tokens_deleted": AccountToken.objects.filter(created_at__lt=before)
            .filter(Q(used_at__isnull=False) | Q(expires_at__lt=timezone.now())).delete()[0],
            "customer_sessions_deleted": CustomerSession.objects.filter(created_at__lt=before)
            .filter(Q(ended_at__isnull=False) | Q(expires_at__lt=timezone.now())).delete()[0],
        }
    run_row = MaintenanceRun.objects.create(
        kind=MaintenanceRun.Kind.RETENTION, started_at=started, finished_at=timezone.now(),
        started_by=started_by, outcome=MaintenanceRun.Outcome.PASSED,
        summary={"older_than": before.isoformat(), "counts": counts})
    audit("security.retention_cleanup", actor_type=(AuditEvent.ActorType.STAFF if started_by
                                                    else AuditEvent.ActorType.SYSTEM),
          actor_id=started_by, target_type="maintenance_run", target_id=run_row.public_id,
          details=counts)
    return run_row
