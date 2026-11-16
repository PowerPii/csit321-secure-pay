"""Reconciliation: status checks on operations the simulator did not answer (UC-28, UC-42).

SIMULATOR-CONTRACT.md section 7, schedule S2 (confirmed by Fifa 13 Nov 2026):

* An operation without a usable answer is `unresolved`. The worker asks the simulator about
  it **with its original operation ID** (`GET /sim/operations/{id}`) after 30 s, 1, 2, 5, 10
  and 20 minutes (+/-10% jitter). It never sends the operation again, so a customer can
  never be charged twice.
* A signed answer settles it exactly as a first answer would: the same apply functions
  (apps.payments.processing, apps.payments.settlement, apps.refunds.service) write the
  status change, the outbox event and the audit entry. `no_record` retires the ID, so the
  payment is declined `not_processed` (or the capture, cancel or refund is not processed).
* Still no answer after the sixth check (about 38.5 minutes): escalated to administrators
  (UC-42), well inside the 1-hour bound of NFR-AVA-03. A `409 operation_id_conflict` is
  escalated at once. An administrator's re-check (FR-TXN-13) is the same status query;
  nobody can set an outcome by hand.
* Restart sweep (FR-TXN-15): an operation still `pending` long after any call could have
  finished was committed but never answered (the process died). It is marked unresolved
  and checked at once.

Several workers can run: an operation is claimed with SKIP LOCKED and leased, like the
webhook outbox.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.payments import processor
from apps.payments.models import Operation, check_delay
from apps.payments.processor import Answer, AnswerKind

logger = logging.getLogger(__name__)

LEASE_SECONDS = 60  # longer than one status query can take (2 s connect + 10 s reply)


def _apply(operation: Operation, answer: Answer, request_id: str = "") -> None:
    """Hand a usable answer to the module that owns this kind of operation."""
    if operation.type == Operation.Type.AUTHORISE:
        from apps.payments.processing import apply_authorise_answer

        apply_authorise_answer(operation.pk, answer, request_id)
    elif operation.type == Operation.Type.REFUND:
        from apps.refunds.service import apply_refund_answer

        apply_refund_answer(operation.pk, answer, request_id)
    else:
        from apps.payments.settlement import apply_settlement_answer

        apply_settlement_answer(operation.pk, answer, request_id)


def _audit(operation: Operation, action: str, actor: tuple[str, str], request_id: str = "",
           **details) -> None:
    payment = operation.payment
    audit(action, actor_type=actor[0], actor_id=actor[1],
          merchant_id=payment.merchant.public_id, target_type="payment",
          target_id=payment.public_id, request_id=request_id,
          details={"operation_id": operation.public_id, "operation_type": operation.type,
                   "checks": operation.reconciliation_checks, **details})


SYSTEM = (AuditEvent.ActorType.SYSTEM, "reconciliation")


def recover_stale_pending(now=None) -> int:
    """FR-TXN-15: operations committed but never answered become unresolved, checked now."""
    now = now or timezone.now()
    rules = settings.GATEWAY_RULES
    cutoff = now - timedelta(seconds=rules["RECONCILIATION_PENDING_STALE_SECONDS"])
    stale = list(Operation.objects.filter(status=Operation.Status.PENDING, created_at__lte=cutoff)
                 .values_list("pk", flat=True)[:settings.WORKER_BATCH_SIZE])
    for pk in stale:
        _apply(Operation.objects.get(pk=pk),
               Answer(AnswerKind.NO_ANSWER, problem="no_answer_recorded"))
        Operation.objects.filter(pk=pk, status=Operation.Status.UNRESOLVED).update(
            next_check_at=now)
    if stale:
        logger.warning("Marked %d operations without an answer as unresolved", len(stale))
    return len(stale)


def claim_due(limit: int, now=None) -> list[int]:
    now = now or timezone.now()
    with transaction.atomic():
        ids = list(Operation.objects.select_for_update(skip_locked=True)
                   .filter(status=Operation.Status.UNRESOLVED, escalated_at__isnull=True)
                   .filter(Q(next_check_at__lte=now) | Q(next_check_at__isnull=True))
                   .order_by("next_check_at").values_list("pk", flat=True)[:limit])
        Operation.objects.filter(pk__in=ids).update(
            next_check_at=now + timedelta(seconds=LEASE_SECONDS))
    return ids


def check(operation_pk: int, actor: tuple[str, str] = SYSTEM, request_id: str = "",
          manual: bool = False) -> Operation:
    """One status query by the original operation ID, then settle, reschedule or escalate.

    `manual` is an administrator's re-check (FR-TXN-13): it also works on an escalated
    operation, and does not count towards the automatic schedule.
    """
    operation = Operation.objects.select_related("payment__merchant").get(pk=operation_pk)
    if operation.status != Operation.Status.UNRESOLVED:
        return operation
    answer = processor.status_query(operation)
    now = timezone.now()
    with transaction.atomic():
        operation = (Operation.objects.select_for_update().select_related("payment__merchant")
                     .get(pk=operation_pk))
        if operation.status != Operation.Status.UNRESOLVED:
            return operation  # settled meanwhile (a late reply or another worker)
        operation.last_checked_at = now
        if not manual:
            operation.reconciliation_checks += 1
        usable = answer.kind is AnswerKind.RECORDED or (
            answer.kind is AnswerKind.CONFLICT and answer.conflict_code == "operation_retired")
        if usable:
            operation.save(update_fields=["last_checked_at", "reconciliation_checks",
                                          "updated_at"])
        elif answer.kind is AnswerKind.CONFLICT:
            # operation_id_conflict: the two systems disagree about the ID itself (UC-42).
            _escalate(operation, now, actor, request_id, problem=answer.conflict_code)
        elif manual:
            operation.save(update_fields=["last_checked_at", "updated_at"])
            _audit(operation, "operation.recheck_no_answer", actor, request_id,
                   problem=answer.problem)
        elif operation.reconciliation_checks >= settings.GATEWAY_RULES[
                "RECONCILIATION_MAX_CHECKS"]:
            _escalate(operation, now, actor, request_id, problem=answer.problem)
        else:
            operation.next_check_at = now + check_delay(operation.reconciliation_checks)
            operation.save(update_fields=["last_checked_at", "reconciliation_checks",
                                          "next_check_at", "updated_at"])
            logger.info("No answer for %s on check %d (%s); next at %s", operation.public_id,
                        operation.reconciliation_checks, answer.problem,
                        operation.next_check_at.isoformat())
    if usable:
        if manual:
            _audit(operation, "operation.rechecked", actor, request_id,
                   simulator_status=(answer.record or {}).get("status"))
        _apply(operation, answer, request_id)
    operation.refresh_from_db()
    return operation


def _escalate(operation: Operation, now, actor, request_id: str, problem: str) -> None:
    """Hand the operation to administrators (UC-42). It stays unresolved: only a signed
    answer from the simulator can settle it, through an administrator's re-check."""
    operation.escalated_at = now
    operation.next_check_at = None
    operation.save(update_fields=["last_checked_at", "reconciliation_checks", "next_check_at",
                                  "escalated_at", "updated_at"])
    _audit(operation, "operation.escalated", actor, request_id, problem=problem)
    logger.error("Escalated %s %s of payment %s after %d checks (%s)", operation.type,
                 operation.public_id, operation.payment.public_id,
                 operation.reconciliation_checks, problem)


def reconcile_due(limit: int | None = None) -> int:
    """The worker job: recover stale operations, then run every status check that is due."""
    recover_stale_pending()
    done = 0
    for pk in claim_due(limit or settings.WORKER_BATCH_SIZE):
        try:
            check(pk)
        except Exception:
            # Leave it leased; it is due again when the lease runs out.
            logger.exception("Status check of operation %s failed", pk)
        done += 1
    return done
