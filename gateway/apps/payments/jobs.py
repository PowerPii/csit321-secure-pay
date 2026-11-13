"""Scheduled payment jobs run by the worker (apps/events/management/commands/run_worker.py)."""
import logging
from datetime import timedelta

from django.conf import settings
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.common.errors import ApiError
from apps.payments import settlement
from apps.payments.models import Operation, OutcomeReason, Payment
from apps.payments.states import PaymentStatus

logger = logging.getLogger(__name__)


def expire_authorisations(limit: int | None = None) -> int:
    """Cancel authorisations not captured within AUTH_EXPIRY_DAYS (FR-TXN-05).

    Sent to the simulator as an ordinary cancel with reason authorisation_expired. Waits
    for a pending capture or cancel to settle first (contract section 3).
    """
    cutoff = timezone.now() - timedelta(days=settings.GATEWAY_RULES["AUTH_EXPIRY_DAYS"])
    open_ops = Operation.objects.filter(payment=OuterRef("pk"),
                                        type__in=settlement.SETTLEMENT_TYPES,
                                        status__in=Operation.OPEN_STATUSES)
    due = (Payment.objects.filter(status=PaymentStatus.AUTHORISED, authorised_at__lte=cutoff)
           .exclude(Exists(open_ops)).order_by("authorised_at")
           .values_list("public_id", flat=True)[:limit or settings.WORKER_BATCH_SIZE])
    actor = settlement.Actor(AuditEvent.ActorType.SYSTEM, "expire_authorisations")
    done = 0
    for payment_id in list(due):
        try:
            operation, created = _start_expiry(payment_id, actor)
        except ApiError:
            continue  # captured, cancelled or picked up by another worker meanwhile
        settlement.settle(operation, created)
        done += 1
    return done


def _start_expiry(payment_id: str, actor):
    return settlement.start(payment_id, Operation.Type.CANCEL, actor,
                            reason=OutcomeReason.AUTHORISATION_EXPIRED, allow_expired=True)


def expire_checkout_sessions(limit: int | None = None) -> int:
    """payment.expired for checkout sessions that passed their hour without a card."""
    from apps.checkout.service import expire_if_due

    due = (Payment.objects.filter(status=PaymentStatus.CREATED,
                                  checkout_expires_at__lte=timezone.now())
           .select_related("merchant").order_by("checkout_expires_at")
           [:limit or settings.WORKER_BATCH_SIZE])
    for payment in due:
        expire_if_due(payment)
    return len(due)
