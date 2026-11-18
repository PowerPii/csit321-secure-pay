"""Staff payment-detail responses, action availability and correlated timelines.

Callers must obtain the payment through the staff access helpers before building a response.
"""
from django.db.models import Q

from apps.accounts.models import StaffAccount
from apps.audit.models import AuditEvent
from apps.common.timefmt import rfc3339
from apps.events.models import OutboxEvent
from apps.internal.serializers import mask_email, payment_row, screening_to_dict
from apps.payments import settlement
from apps.payments.models import Operation, Payment
from apps.payments.serializers import payment_to_dict
from apps.payments.states import PaymentStatus
from apps.refunds.models import Refund
from apps.refunds.serializers import refund_to_dict
from apps.risk.models import ScreeningEvent


def _payment_audit(payment: Payment):
    """Every audit entry about the payment: by correlation ID (FR-TXN-16), and for entries
    written before correlation IDs existed, by target or the refund's payment_id."""
    return (AuditEvent.objects.filter(
        Q(correlation_id=payment.public_id) | Q(target_id=payment.public_id)
        | Q(target_type="refund", details__payment_id=payment.public_id))
        .order_by("occurred_at", "id"))


# Audit actions that describe the payment's own history (D4 "Status history").
def timeline(payment: Payment) -> list[dict]:
    events = list(_payment_audit(payment))
    staff_ids = {e.actor_id for e in events if e.actor_type == AuditEvent.ActorType.STAFF}
    names = dict(StaffAccount.objects.filter(public_id__in=staff_ids)
                 .values_list("public_id", "user__email"))
    out = []
    for event in events:
        if event.action == "payment.viewed":
            continue  # access log, not history
        actor = event.actor_id
        if event.actor_type == AuditEvent.ActorType.STAFF:
            actor = names.get(event.actor_id, event.actor_id)
        out.append({
            "at": rfc3339(event.occurred_at),
            "action": event.action,
            "actor_type": event.actor_type,
            "actor": actor or None,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "details": event.details,
        })
    return out


def webhooks(payment: Payment) -> list[dict]:
    out = []
    for event in (OutboxEvent.objects.filter(payment=payment)
                  .prefetch_related("attempts").order_by("sequence")):
        attempts = list(event.attempts.all())
        last = attempts[-1] if attempts else None
        out.append({
            "id": event.public_id,
            "type": event.type,
            "sequence": event.sequence,
            "status": event.status,
            "attempts": event.attempt_count,
            "last_http_status": last.http_status if last else None,
            "last_error": (last.error or None) if last else None,
            "next_attempt_at": rfc3339(event.next_attempt_at)
            if event.status == OutboxEvent.Status.PENDING else None,
            "delivered_at": rfc3339(event.delivered_at),
        })
    return out


def trail(payment: Payment, screening, ops: list[Operation], refunds: list[Refund],
          hooks: list[dict]) -> list[dict]:
    """FR-TXN-16: one timeline of everything linked by the payment's correlation ID: the
    screening decision, processing operations, refunds, notifications (webhooks and
    emails) and audit entries, oldest first. Email addresses are never included."""
    from apps.events.models import OutboundEmail

    rows = [{"at": payment.created_at, "kind": "payment", "id": payment.public_id,
             "title": "Payment created", "status": "created", "request_id": None}]
    if screening is not None:
        rows.append({"at": screening.occurred_at, "kind": "screening",
                     "id": screening.public_id, "title": f"Screening: {screening.outcome}",
                     "status": screening.outcome, "request_id": None,
                     "detail": (f"score {screening.score:.4f}" if screening.score is not None
                                else None)})
    for op in ops:
        rows.append({"at": op.created_at, "kind": "operation", "id": op.public_id,
                     "title": f"{op.type.capitalize()} sent to the processor",
                     "status": op.status, "request_id": None})
    for refund in refunds:
        rows.append({"at": refund.created_at, "kind": "refund", "id": refund.public_id,
                     "title": f"Refund {refund.reference}", "status": refund.status,
                     "request_id": None})
    events = {e.public_id: e for e in payment.events.all()}
    for hook in hooks:
        rows.append({"at": events[hook["id"]].created_at, "kind": "webhook",
                     "id": hook["id"], "title": f"Webhook {hook['type']}",
                     "status": hook["status"], "request_id": None,
                     "detail": f"{hook['attempts']} attempt(s)"})
    for email in OutboundEmail.objects.filter(payment=payment).order_by("created_at", "id"):
        rows.append({"at": email.created_at, "kind": "email", "id": email.public_id,
                     "title": f"Email to customer: {email.get_kind_display()}",
                     "status": email.status, "request_id": None})
    for event in _payment_audit(payment):
        rows.append({"at": event.occurred_at, "kind": "audit", "id": str(event.pk),
                     "title": event.action, "status": None,
                     "request_id": event.request_id or None,
                     "actor_type": event.actor_type})
    order = {"payment": 0, "screening": 1, "operation": 2, "refund": 3, "webhook": 4,
             "email": 5, "audit": 6}
    rows.sort(key=lambda r: (r["at"], order[r["kind"]]))
    for row in rows:
        row["at"] = rfc3339(row["at"])
        row["correlation_id"] = payment.public_id
    return rows


def operation_to_dict(op: Operation) -> dict:
    return {
        "id": op.public_id,
        "type": op.type,
        "status": op.status,
        "amount": op.amount,
        "simulator_reference": op.simulator_reference or None,
        "reconciliation_checks": op.reconciliation_checks,
        "last_checked_at": rfc3339(op.last_checked_at),
        "next_check_at": rfc3339(op.next_check_at)
        if op.status == Operation.Status.UNRESOLVED else None,
        "escalated_at": rfc3339(op.escalated_at),
        "created_at": rfc3339(op.created_at),
        "completed_at": rfc3339(op.completed_at),
    }


def allowed_actions(staff: StaffAccount, payment: Payment, ops: list[Operation],
                    refundable: int) -> dict:
    open_settlement = any(op.type in settlement.SETTLEMENT_TYPES
                          and op.status in Operation.OPEN_STATUSES for op in ops)
    unresolved = any(op.status == Operation.Status.UNRESOLVED for op in ops)
    authorised = payment.status == PaymentStatus.AUTHORISED and not open_settlement
    return {
        "capture": staff.is_operator and authorised,
        "cancel": staff.is_operator and authorised,
        "refund": (staff.is_operator and payment.status == PaymentStatus.CAPTURED
                   and refundable > 0 and not unresolved),
        "recheck": staff.is_admin and unresolved,
        "review": not staff.is_operator and payment.screening_decision in ("verify", "block"),
    }


def payment_detail(staff: StaffAccount, payment: Payment) -> dict:
    data = payment_to_dict(payment)
    ops = list(payment.operations.order_by("created_at", "id"))
    screening = ScreeningEvent.objects.filter(payment=payment).first()
    refunds = list(Refund.objects.filter(payment=payment).select_related("payment"))
    refund_rows = [refund_to_dict(r) for r in refunds]
    hooks = webhooks(payment)
    data.update({
        "merchant": {"id": payment.merchant.public_id, "name": payment.merchant.name},
        "customer": mask_email(payment.customer_email),
        "description": payment.description or None,
        "screening": screening_to_dict(screening, merchant_view=staff.is_operator),
        "screening_decision": payment.screening_decision or None,
        "verification": payment_row(payment)["risk"]["verification"]
        if payment.screening_decision else None,
        "operations": [operation_to_dict(op) for op in ops],
        "refunds": refund_rows,
        "webhooks": hooks,
        "timeline": timeline(payment),
        "correlation_id": payment.public_id,
        "trail": trail(payment, screening, ops, refunds, hooks),
        "actions": allowed_actions(staff, payment, ops, data["refundable_amount"]),
    })
    return data
