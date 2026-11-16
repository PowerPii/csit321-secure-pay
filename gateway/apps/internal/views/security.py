"""Security alerts for administrators (FR-ADM-08, UC-40; NFR-PER-03).

* GET  security/alerts?status=open|resolved|all&kind=&page= : newest activity first.
* GET  security/alerts/open-count : the sidebar badge; polled every 5 s.
* GET  security/alerts/{id} : the alert with the audit entries around it (same source).
* POST security/alerts/{id}/resolve {note} : resolve with a note (audited).
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.common.errors import ApiError, invalid, not_found
from apps.common.timefmt import rfc3339
from apps.internal.access import ADMIN, StaffAPIView
from apps.internal.views.payments import _int
from apps.security.models import AlertKind, SecurityAlert

RELATED_WINDOW = timedelta(hours=1)
RELATED_LIMIT = 50


def alert_to_dict(alert: SecurityAlert) -> dict:
    return {
        "id": alert.public_id,
        "kind": alert.kind,
        "kind_label": AlertKind(alert.kind).label if alert.kind in AlertKind.values
        else alert.kind,
        "severity": alert.severity,
        "source": alert.source,
        "merchant_id": alert.merchant_id or None,
        "summary": alert.summary,
        "details": alert.details,
        "count": alert.count,
        "first_seen_at": rfc3339(alert.first_seen_at),
        "last_seen_at": rfc3339(alert.last_seen_at),
        "status": alert.status,
        "resolved_by": (alert.resolved_by.display_name if alert.resolved_by_id else None),
        "resolved_at": rfc3339(alert.resolved_at),
        "resolution_note": alert.resolution_note or None,
    }


def _audit_row(e: AuditEvent) -> dict:
    return {"id": e.pk, "at": rfc3339(e.occurred_at), "action": e.action,
            "actor_type": e.actor_type, "actor_id": e.actor_id or None,
            "merchant_id": e.merchant_id or None, "target_type": e.target_type or None,
            "target_id": e.target_id or None, "request_id": e.request_id or None,
            "details": e.details}


def _get(alert_id: str, lock=False) -> SecurityAlert:
    alerts = SecurityAlert.objects.select_related("resolved_by__user")
    if lock:
        alerts = alerts.select_for_update(of=("self",))
    alert = alerts.filter(public_id=alert_id[:32]).first()
    if alert is None:
        raise not_found()
    return alert


class SecurityAlertListView(StaffAPIView):
    roles = ADMIN

    def get(self, request):
        params = request.query_params
        show = params.get("status") or "open"
        if show not in ("open", "resolved", "all"):
            raise invalid("invalid_field", "'status' must be open, resolved or all.",
                          param="status")
        alerts = SecurityAlert.objects.select_related("resolved_by__user")
        if show != "all":
            alerts = alerts.filter(status=show)
        if params.get("kind"):
            alerts = alerts.filter(kind=params["kind"][:32])
        page = _int(params.get("page"), "page", 1, 1, 100_000)
        size = _int(params.get("page_size"), "page_size", 25, 1, 100)
        count = alerts.count()
        rows = alerts.order_by("-last_seen_at", "-id")[(page - 1) * size: page * size]
        return Response({"object": "list", "count": count, "page": page, "page_size": size,
                         "open": SecurityAlert.objects.filter(status="open").count(),
                         "data": [alert_to_dict(a) for a in rows]})


class SecurityAlertOpenCountView(StaffAPIView):
    roles = ADMIN

    def get(self, request):
        open_alerts = SecurityAlert.objects.filter(status=SecurityAlert.Status.OPEN)
        latest = open_alerts.order_by("-last_seen_at").values_list("last_seen_at", flat=True) \
            .first()
        return Response({"open": open_alerts.count(), "latest_at": rfc3339(latest)})


class SecurityAlertDetailView(StaffAPIView):
    """The alert and the audit entries by or about its source around the time it covers."""

    roles = ADMIN

    def get(self, request, alert_id: str):
        alert = _get(alert_id)
        related = (AuditEvent.objects
                   .filter(Q(actor_id=alert.source) | Q(target_id=alert.source)
                           | Q(target_id=alert.public_id))
                   .filter(occurred_at__gte=alert.first_seen_at - RELATED_WINDOW,
                           occurred_at__lte=(alert.resolved_at or timezone.now())
                           + timedelta(seconds=1))
                   .order_by("-occurred_at", "-id")[:RELATED_LIMIT])
        data = alert_to_dict(alert)
        data["related_audit"] = [_audit_row(e) for e in related]
        return Response(data)


class SecurityAlertResolveView(StaffAPIView):
    roles = ADMIN

    def post(self, request, alert_id: str):
        body = request.data if isinstance(request.data, dict) else {}
        note = body.get("note")
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 1000:
            raise invalid("missing_field", "Add a note of up to 1000 characters on what you "
                          "found or did.", param="note")
        with transaction.atomic():
            alert = _get(alert_id, lock=True)
            if alert.status == SecurityAlert.Status.RESOLVED:
                raise ApiError(409, "alert_resolved", "This alert is already resolved.")
            alert.status = SecurityAlert.Status.RESOLVED
            alert.resolved_by = self.staff
            alert.resolved_at = timezone.now()
            alert.resolution_note = note.strip()
            alert.save(update_fields=["status", "resolved_by", "resolved_at",
                                      "resolution_note"])
            audit("security_alert.resolved", actor_type=AuditEvent.ActorType.STAFF,
                  actor_id=self.staff.public_id, merchant_id=alert.merchant_id,
                  target_type="security_alert", target_id=alert.public_id,
                  request_id=request.request_id,
                  details={"kind": alert.kind, "count": alert.count, "note": note.strip()})
        return Response(alert_to_dict(alert))
