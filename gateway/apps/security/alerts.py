"""Raise a security alert (FR-ADM-08, UC-39).

    raise_alert(kind, severity=..., source=..., summary=..., details=...) -> SecurityAlert

An open alert of the same kind and source seen within SECURITY_ALERT_GROUP_MINUTES takes the
new event: its count goes up and nothing else is sent. Otherwise a new alert is created and
every active administrator is emailed through the outbox, which retries a failed send and
keeps the alert on the dashboard either way (UC-39 alternative flow). The dashboard polls the
open count every 5 s, so an alert shows within 10 s (NFR-PER-03).

Call it inside the transaction that records the event, or on its own; it never raises for a
mail problem. Never put card data or secrets in `details`.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.security.models import AlertKind, SecurityAlert


def _group_window() -> timedelta:
    return timedelta(minutes=settings.GATEWAY_RULES["SECURITY_ALERT_GROUP_MINUTES"])


def raise_alert(kind: str, *, severity: str, source: str, summary: str,
                merchant_id: str = "", details: dict | None = None) -> SecurityAlert:
    now = timezone.now()
    with transaction.atomic():
        alert = (SecurityAlert.objects.select_for_update()
                 .filter(kind=kind, source=source[:80], status=SecurityAlert.Status.OPEN,
                         last_seen_at__gte=now - _group_window())
                 .order_by("-last_seen_at").first())
        if alert is not None:
            alert.count += 1
            alert.last_seen_at = now
            alert.details = details or {}
            alert.summary = summary[:300]
            alert.save(update_fields=["count", "last_seen_at", "details", "summary"])
            return alert
        alert = SecurityAlert.objects.create(
            kind=kind, severity=severity, source=source[:80], merchant_id=merchant_id,
            summary=summary[:300], details=details or {}, last_seen_at=now)
        audit("security_alert.raised", actor_type=AuditEvent.ActorType.SYSTEM,
              actor_id="security", merchant_id=merchant_id, target_type="security_alert",
              target_id=alert.public_id,
              details={"kind": kind, "severity": severity, "source": source[:80]})
        _email_administrators(alert)
    return alert


def _email_administrators(alert: SecurityAlert) -> None:
    from apps.accounts import mail

    label = AlertKind(alert.kind).label if alert.kind in AlertKind.values else alert.kind
    mail.notify_administrators(
        f"security alert: {label.lower()}",
        f"Hello,\n\nSecurePay raised a {alert.severity}-severity security alert.\n\n"
        f"{alert.summary}\n\nSource: {alert.source}\nAlert: {alert.public_id}\n\n"
        "Repeats of the same event are added to this alert rather than emailed again. "
        f"Review and resolve it at {mail.dashboard_link('security')}.")
