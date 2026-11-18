"""Webhook delivery log (extends FR-TXN-06/07; API-CONTRACT.md section 7).

Merchant operators see the webhook events of their own merchant; administrators see every
merchant's (and may filter by one). Fraud analysts have no use for it and are refused.

* GET  webhooks?status=pending|delivered|undelivered&type=&q=&merchant=&page=&page_size=
       newest first; q matches an event ID (evt_...) or payment ID (pay_...).
* GET  webhooks/{event_id} : the event, its payload and every delivery attempt.
* POST webhooks/{event_id}/resend : put a delivered or undelivered event back in the queue
       with the same event ID and payload (merchants drop repeats by event ID). Audited.

Another merchant's event answers 404, exactly like one that does not exist (FR-MER-08).
"""
from django.conf import settings
from django.db import transaction
from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.events import delivery
from apps.events.models import EventType, OutboxEvent
from apps.internal.access import StaffAPIView
from apps.internal.query_params import bounded_int

OPERATOR_OR_ADMIN = (Role.MERCHANT_OPERATOR, Role.ADMINISTRATOR)
STATUSES = {s.value for s in OutboxEvent.Status}


def _visible(staff):
    events = OutboxEvent.objects.select_related("merchant", "payment")
    if staff.is_operator:
        return events.filter(merchant_id=staff.merchant_id)
    return events


def _get(staff, event_id: str) -> OutboxEvent:
    event = (_visible(staff).prefetch_related("attempts")
             .filter(public_id=event_id[:32]).first())
    if event is None:
        raise not_found()
    return event


def attempt_to_dict(attempt) -> dict:
    return {
        "number": attempt.attempt_number,
        "at": rfc3339(attempt.started_at),
        "http_status": attempt.http_status,
        "error": attempt.error or None,
        "duration_ms": attempt.duration_ms,
        "succeeded": attempt.succeeded,
        "response_excerpt": attempt.response_excerpt or None,
        "manual": attempt.manual,
    }


def event_row(event: OutboxEvent, last=None) -> dict:
    return {
        "id": event.public_id,
        "type": event.type,
        "payment_id": event.payment.public_id,
        "merchant_id": event.merchant.public_id,
        "merchant_name": event.merchant.name,
        "sequence": event.sequence,
        "status": event.status,
        "attempts": event.attempt_count,
        "resends": event.resend_count,
        "last_http_status": last.http_status if last else None,
        "last_error": (last.error or None) if last else None,
        "last_attempt_at": rfc3339(last.started_at) if last else None,
        "next_attempt_at": rfc3339(event.next_attempt_at)
        if event.status == OutboxEvent.Status.PENDING else None,
        "created_at": rfc3339(event.created_at),
        "delivered_at": rfc3339(event.delivered_at),
    }


def can_resend(event: OutboxEvent) -> bool:
    merchant = event.merchant
    return (event.status != OutboxEvent.Status.PENDING
            and bool(merchant.webhook_url) and merchant.webhook_url_approved
            and event.resend_count < settings.GATEWAY_RULES["WEBHOOK_MAX_MANUAL_RESENDS"])


def event_detail(event: OutboxEvent) -> dict:
    attempts = sorted(event.attempts.all(), key=lambda a: a.attempt_number)
    data = event_row(event, attempts[-1] if attempts else None)
    merchant = event.merchant
    data.update({
        "endpoint": merchant.webhook_url or None,
        "endpoint_approved": merchant.webhook_url_approved,
        "payload": event.payload,
        "attempt_log": [attempt_to_dict(a) for a in reversed(attempts)],  # newest first
        "can_resend": can_resend(event),
        "max_resends": settings.GATEWAY_RULES["WEBHOOK_MAX_MANUAL_RESENDS"],
    })
    return data


class WebhookListView(StaffAPIView):
    roles = OPERATOR_OR_ADMIN

    def get(self, request):
        params = request.query_params
        events = _visible(self.staff)
        show = params.get("status") or ""
        if show and show not in STATUSES:
            raise invalid("invalid_field",
                          "'status' must be pending, delivered or undelivered.", param="status")
        if show:
            events = events.filter(status=show)
        kind = params.get("type") or ""
        if kind and kind not in EventType.values:
            raise invalid("invalid_field", "'type' is not a known event type.", param="type")
        if kind:
            events = events.filter(type=kind)
        q = (params.get("q") or "").strip()[:32]
        if q.startswith("evt_"):
            events = events.filter(public_id=q)
        elif q:
            events = events.filter(payment__public_id=q)
        merchant = params.get("merchant") or ""
        if merchant and not self.staff.is_operator:
            events = events.filter(merchant__public_id=merchant[:32])
        page = bounded_int(params.get("page"), "page", 1, 1, 100_000)
        size = bounded_int(params.get("page_size"), "page_size", 25, 1, 100)
        count = events.count()
        rows = list(events.prefetch_related("attempts")
                    .order_by("-created_at", "-id")[(page - 1) * size: page * size])
        counts = dict.fromkeys(sorted(STATUSES), 0)
        for row in _visible(self.staff).order_by().values("status").annotate(n=Count("id")):
            counts[row["status"]] = row["n"]
        endpoint = None
        if self.staff.is_operator:
            m = self.staff.merchant
            endpoint = {"url": m.webhook_url or None, "approved": m.webhook_url_approved}
        data = []
        for event in rows:
            attempts = list(event.attempts.all())
            data.append(event_row(event, max(attempts, key=lambda a: a.attempt_number)
                                  if attempts else None))
        return Response({"object": "list", "count": count, "page": page, "page_size": size,
                         "counts": counts, "endpoint": endpoint,
                         "event_types": EventType.values, "data": data})


class WebhookDetailView(StaffAPIView):
    roles = OPERATOR_OR_ADMIN

    def get(self, request, event_id: str):
        return Response(event_detail(_get(self.staff, event_id)))


class WebhookResendView(StaffAPIView):
    roles = OPERATOR_OR_ADMIN

    def post(self, request, event_id: str):
        event = _get(self.staff, event_id)
        with transaction.atomic():
            try:
                event, previous = delivery.requeue(event.pk)
            except delivery.ResendRefused as exc:
                raise ApiError(409, exc.code, exc.message) from None
            audit("webhook.resent", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=self.staff.public_id, merchant_id=event.merchant.public_id,
                  target_type="event", target_id=event.public_id,
                  request_id=request.request_id, correlation_id=event.payment.public_id,
                  details={"type": event.type, "previous_status": previous,
                           "attempts_before": event.attempt_count,
                           "resend_number": event.resend_count})
        return Response(event_detail(_get(self.staff, event_id)),
                        status=status.HTTP_202_ACCEPTED)
