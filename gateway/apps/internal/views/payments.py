"""D3 payments list, D4 payment detail, D5 refund, capture / cancel and operation re-check.

Merchant operators act on their own merchant's payments. Analysts and administrators see
every merchant read-only (FR-ADM-06), and each detail view they open is audited. Capture,
cancel and refund go through the same service functions as the merchant API, so the rules,
row locks, outbox events and audit entries are identical (actor type "staff").
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import IntegerField, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from apps.accounts.models import StaffAccount
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.common.views import body_or_empty
from apps.events.models import OutboxEvent
from apps.internal.access import ADMIN, OPERATOR, StaffAPIView, get_payment, visible_payments
from apps.internal.serializers import mask_email, payment_row, screening_to_dict
from apps.payments import reconciliation, settlement
from apps.payments.models import Operation, Payment
from apps.payments.serializers import payment_to_dict
from apps.payments.states import PaymentStatus
from apps.refunds import service as refunds
from apps.refunds.models import Refund
from apps.refunds.serializers import refund_to_dict
from apps.risk.models import ScreeningEvent

MAX_PAGE_SIZE = 100
DECISIONS = {"allow", "verify", "verify_passed", "verify_failed", "block", "not_screened"}


def local_zone() -> ZoneInfo:
    return ZoneInfo(settings.DASHBOARD_TIME_ZONE)


def _date(value: str, param: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise invalid("invalid_field", f"'{param}' must be a date like 2026-11-13.",
                      param=param) from None


def _int(value, param, default, low, high):
    if value in (None, ""):
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise invalid("invalid_field", f"'{param}' must be a whole number.", param=param) \
            from None
    return max(low, min(high, number))


def _completed_refunds():
    return Coalesce(Subquery(
        Refund.objects.filter(payment=OuterRef("pk"), status=Refund.Status.COMPLETED)
        .values("payment").annotate(total=Sum("amount")).values("total")[:1],
        output_field=IntegerField()), 0)


def _escalated_ops():
    return Operation.objects.filter(status=Operation.Status.UNRESOLVED,
                                    escalated_at__isnull=False)


def filter_payments(payments, params, staff: StaffAccount):
    statuses = [s for s in (params.get("status") or "").split(",") if s]
    for value in statuses:
        if value not in {s.value for s in PaymentStatus}:
            raise invalid("invalid_field", f"Unknown status '{value}'.", param="status")
    if statuses:
        payments = payments.filter(status__in=statuses)

    decision = params.get("decision") or ""
    if decision:
        if decision not in DECISIONS:
            raise invalid("invalid_field", f"Unknown risk decision '{decision}'.",
                          param="decision")
        if decision == "verify_passed":
            payments = payments.filter(
                screening_decision="verify",
                status__in=[PaymentStatus.PROCESSING, PaymentStatus.AUTHORISED,
                            PaymentStatus.CAPTURED, PaymentStatus.DECLINED,
                            PaymentStatus.UNRESOLVED, PaymentStatus.CANCELLED])
        elif decision == "verify_failed":
            payments = payments.filter(screening_decision="verify",
                                       status=PaymentStatus.BLOCKED)
        else:
            payments = payments.filter(screening_decision=decision)

    zone = local_zone()
    if params.get("from"):
        start = datetime.combine(_date(params["from"], "from"), time.min, zone)
        payments = payments.filter(created_at__gte=start)
    if params.get("to"):
        end = datetime.combine(_date(params["to"], "to") + timedelta(days=1), time.min, zone)
        payments = payments.filter(created_at__lt=end)

    query = (params.get("q") or "").strip()[:254]
    if query:
        match = (Q(reference__iexact=query) | Q(public_id=query)
                 | Q(order_reference__icontains=query))
        if "@" in query:
            match |= Q(customer_email__iexact=query)
        payments = payments.filter(match)

    merchant = params.get("merchant") or ""
    if merchant and not staff.is_operator:
        payments = payments.filter(merchant__public_id=merchant)

    if params.get("attention") == "escalated":
        payments = payments.filter(pk__in=_escalated_ops().values("payment_id"))
    return payments


def summary(staff: StaffAccount) -> dict:
    """The tiles above the D3 table, for what this staff member can see."""
    payments = visible_payments(staff)
    zone = local_zone()
    now = timezone.now().astimezone(zone)
    today = datetime.combine(now.date(), time.min, zone)
    month = datetime.combine(now.date().replace(day=1), time.min, zone)
    refunds_qs = Refund.objects.filter(status=Refund.Status.COMPLETED, completed_at__gte=month)
    if staff.is_operator:
        refunds_qs = refunds_qs.filter(payment__merchant_id=staff.merchant_id)
    unresolved_ops = Operation.objects.filter(status=Operation.Status.UNRESOLVED,
                                              payment__in=payments)
    return {
        "awaiting_capture": payments.filter(status=PaymentStatus.AUTHORISED).count(),
        "unresolved": payments.filter(Q(status=PaymentStatus.UNRESOLVED)
                                      | Q(pk__in=unresolved_ops.values("payment_id")))
        .distinct().count(),
        "blocked_today": payments.filter(status=PaymentStatus.BLOCKED,
                                         created_at__gte=today).count(),
        "refunded_this_month": refunds_qs.aggregate(total=Sum("amount"))["total"] or 0,
        "escalated": (_escalated_ops().filter(payment__in=payments).count()
                      if not staff.is_operator else None),
    }


class PaymentListView(StaffAPIView):
    """GET ?status=&decision=&from=&to=&q=&merchant=&attention=escalated&page=&page_size="""

    def get(self, request):
        params = request.query_params
        payments = filter_payments(visible_payments(self.staff), params, self.staff)
        page = _int(params.get("page"), "page", 1, 1, 100_000)
        size = _int(params.get("page_size"), "page_size", 25, 1, MAX_PAGE_SIZE)
        count = payments.count()
        rows = (payments.annotate(refunded=_completed_refunds())
                .order_by("-created_at", "-id")[(page - 1) * size: page * size])
        return Response({
            "object": "list",
            "count": count,
            "page": page,
            "page_size": size,
            "data": [payment_row(p, p.refunded) for p in rows],
            "summary": summary(self.staff),
        })


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
        "screening": screening_to_dict(screening),
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


class PaymentDetailView(StaffAPIView):
    def get(self, request, payment_id: str):
        payment = get_payment(self.staff, payment_id)
        if not self.staff.is_operator:
            # FR-ADM-06: each cross-merchant view by an administrator or analyst is logged.
            audit("payment.viewed", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=self.staff.public_id, merchant_id=payment.merchant.public_id,
                  target_type="payment", target_id=payment.public_id,
                  request_id=request.request_id)
        return Response(payment_detail(self.staff, payment))


class _SettleView(StaffAPIView):
    """Capture or cancel from D4. 200 when the simulator confirmed it; 202 when it did not
    answer (the operation is unresolved and reconciliation finishes it)."""

    roles = OPERATOR
    op_type = ""

    def post(self, request, payment_id: str):
        payment = get_payment(self.staff, payment_id)
        body = body_or_empty(request)
        operation, created = settlement.start(payment.public_id, self.op_type, self.actor(),
                                              merchant=self.staff.merchant, body=dict(body))
        payment, operation = settlement.settle(operation, created, request.request_id)
        if operation.status == Operation.Status.NOT_PROCESSED:
            raise ApiError(409, "operation_not_processed",
                           "The processor has no record of this request, so nothing changed. "
                           "Try again.")
        if operation.status == Operation.Status.FAILED:
            raise ApiError(409, "processor_rejected",
                           f"The processor refused the {self.op_type}. Nothing changed; an "
                           "administrator has been told.")
        code = (status.HTTP_200_OK if operation.status == Operation.Status.SUCCEEDED
                else status.HTTP_202_ACCEPTED)
        return Response(payment_detail(self.staff, payment), status=code)


class CaptureView(_SettleView):
    op_type = Operation.Type.CAPTURE


class CancelView(_SettleView):
    op_type = Operation.Type.CANCEL


class RefundView(StaffAPIView):
    """D5. POST {amount, reason}: 201 with the refund (completed, failed or unresolved).
    GET: the payment's refunds and the refundable amount."""

    roles = OPERATOR

    def get(self, request, payment_id: str):
        payment = get_payment(self.staff, payment_id)
        return Response({
            "object": "list",
            "payment_id": payment.public_id,
            "refundable_amount": refunds.refundable_amount(payment),
            "data": [refund_to_dict(r) for r in
                     Refund.objects.filter(payment=payment).select_related("payment")],
        })

    def post(self, request, payment_id: str):
        payment = get_payment(self.staff, payment_id)
        body = body_or_empty(request)
        refund, created = refunds.start(payment.public_id, self.staff.merchant, dict(body),
                                        self.actor())
        refund = refunds.submit(refund, created, request.request_id)
        return Response(refund_to_dict(refund), status=status.HTTP_201_CREATED)


class OperationRecheckView(StaffAPIView):
    """FR-TXN-13 / UC-42: an administrator asks the simulator again about an unresolved
    operation, by its original ID. Only a signed answer can settle it; nobody sets an
    outcome by hand."""

    roles = ADMIN

    def post(self, request, operation_id: str):
        operation = Operation.objects.filter(public_id=operation_id).first()
        if operation is None:
            raise not_found()
        if operation.status != Operation.Status.UNRESOLVED:
            raise ApiError(409, "operation_not_unresolved",
                           f"This operation is already {operation.status}.")
        result = reconciliation.check(
            operation.pk, actor=(AuditEvent.ActorType.STAFF, self.staff.public_id),
            request_id=request.request_id, manual=True)
        return Response({"operation": operation_to_dict(result),
                         "settled": result.status != Operation.Status.UNRESOLVED})
