"""Apply a simulator answer to an authorise operation and its payment (SIMULATOR-CONTRACT.md 7).

Shared by checkout (the first answer) and reconciliation (sprint 5, status queries), so
both settle a payment the same way. Each change goes through check_transition, writes the
outbox event in the same transaction and an audit entry quoting the simulator reference.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.events.models import EventType
from apps.events.outbox import record_payment_event
from apps.payments.models import Operation, OutcomeReason, Payment
from apps.payments.processor import Answer, AnswerKind
from apps.payments.states import PaymentStatus, check_transition

logger = logging.getLogger(__name__)


def _move(payment: Payment, target: PaymentStatus, event: EventType) -> None:
    check_transition(PaymentStatus(payment.status), target)
    payment.status = target
    record_payment_event(payment, event)  # saves the payment


def apply_authorise_answer(operation_id: int, answer: Answer, request_id: str = "") -> Payment:
    with transaction.atomic():
        operation = Operation.objects.select_for_update().get(pk=operation_id)
        payment = Payment.objects.select_for_update().get(pk=operation.payment_id)
        if operation.status not in Operation.OPEN_STATUSES:
            return payment  # already settled (a late or repeated answer changes nothing)

        record = answer.record
        if answer.kind is AnswerKind.CONFLICT and answer.conflict_code == "operation_retired":
            # The gateway never resends, so this is a bug; the record inside is still final.
            logger.error("Simulator says %s was retired", operation.public_id)
        elif answer.kind is AnswerKind.CONFLICT:
            logger.error("Simulator reports %s for %s", answer.conflict_code,
                         operation.public_id)
            record = None  # operation_id_conflict: leave it unresolved and escalate (UC-43)

        now = timezone.now()
        if record is None:
            operation.mark_unresolved()
            if payment.status != PaymentStatus.UNRESOLVED:
                _move(payment, PaymentStatus.UNRESOLVED, EventType.PAYMENT_UNRESOLVED)
            action, details = "payment.unresolved", {"problem": answer.problem or
                                                     answer.conflict_code}
        else:
            operation.simulator_reference = record.get("simulator_reference") or ""
            operation.evidence_body = answer.raw_body
            operation.evidence_signature = answer.signature
            operation.completed_at = now
            status = record.get("status")
            if status == "approved":
                operation.status = Operation.Status.SUCCEEDED
                payment.authorised_at = now
                _move(payment, PaymentStatus.AUTHORISED, EventType.PAYMENT_AUTHORISED)
                action = "payment.authorised"
                from apps.guest.receipts import queue_receipt

                queue_receipt(payment)  # FR-CHK-15, sent by the worker after the commit
            elif status == "declined":
                operation.status = Operation.Status.FAILED
                payment.outcome_reason = OutcomeReason.CARD_DECLINED
                _move(payment, PaymentStatus.DECLINED, EventType.PAYMENT_DECLINED)
                action = "payment.declined"
            else:  # no_record: the simulator never received it; retired, never resent
                operation.status = Operation.Status.NOT_PROCESSED
                payment.outcome_reason = OutcomeReason.NOT_PROCESSED
                _move(payment, PaymentStatus.DECLINED, EventType.PAYMENT_DECLINED)
                action = "payment.declined"
            operation.save()
            details = {"simulator_reference": operation.simulator_reference or None,
                       "simulator_status": status,
                       "decline_reason": record.get("decline_reason")}

        audit(action, actor_type=AuditEvent.ActorType.SYSTEM, actor_id="processor",
              merchant_id=payment.merchant.public_id, target_type="payment",
              target_id=payment.public_id, request_id=request_id,
              details={"operation_id": operation.public_id, **details})
        return payment
