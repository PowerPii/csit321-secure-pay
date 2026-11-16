"""Cross-merchant access attempts (FR-MER-09, UC-21).

A merchant (by API key) or a merchant operator (in the dashboard) who asks for a payment or
refund that belongs to another merchant gets "not found", exactly as if it did not exist
(FR-MER-08). Behind that reply the attempt is written to the audit log, and once the same
caller has made CROSS_MERCHANT_ALERT_ATTEMPTS attempts within
CROSS_MERCHANT_ALERT_WINDOW_MINUTES, administrators get a security alert (grouped, so later
attempts add to its count).

    log_if_cross_merchant(request, view_kwargs, merchant, actor_type, actor_id)

is called by the merchant API and staff API base views when a request ends in 404.
"""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.audit.models import record as audit
from apps.security.alerts import raise_alert
from apps.security.models import AlertKind, Severity

ACTION = "security.cross_merchant_access"


def _owner(view_kwargs: dict) -> tuple[str, str, str] | None:
    """(target_type, target_id, owning merchant's public ID) for the record the URL names."""
    from apps.payments.models import Payment
    from apps.refunds.models import Refund

    payment_id = view_kwargs.get("payment_id")
    if isinstance(payment_id, str) and payment_id:
        owner = (Payment.objects.filter(public_id=payment_id[:32])
                 .values_list("merchant__public_id", flat=True).first())
        return ("payment", payment_id[:32], owner) if owner else None
    refund_id = view_kwargs.get("refund_id")
    if isinstance(refund_id, str) and refund_id:
        owner = (Refund.objects.filter(public_id=refund_id[:32])
                 .values_list("payment__merchant__public_id", flat=True).first())
        return ("refund", refund_id[:32], owner) if owner else None
    return None


def log_if_cross_merchant(request, view_kwargs: dict, merchant, actor_type: str,
                          actor_id: str) -> bool:
    """Record the attempt if the 404 hid another merchant's record. Returns True if it did."""
    if merchant is None or not view_kwargs:
        return False
    found = _owner(view_kwargs)
    if found is None:
        return False
    target_type, target_id, owner = found
    if owner == merchant.public_id:
        return False  # a 404 for some other reason (e.g. a refund route on the wrong payment)
    audit(ACTION, actor_type=actor_type, actor_id=actor_id, merchant_id=merchant.public_id,
          target_type=target_type, target_id=target_id,
          request_id=getattr(request, "request_id", ""),
          details={"method": request.method, "path": request.path[:200],
                   "owner_merchant_id": owner})
    rules = settings.GATEWAY_RULES
    since = timezone.now() - timedelta(minutes=rules["CROSS_MERCHANT_ALERT_WINDOW_MINUTES"])
    attempts = AuditEvent.objects.filter(action=ACTION, actor_id=actor_id,
                                         occurred_at__gte=since).count()
    if attempts >= rules["CROSS_MERCHANT_ALERT_ATTEMPTS"]:
        who = "API key" if actor_type == AuditEvent.ActorType.MERCHANT_API else "Operator"
        raise_alert(
            AlertKind.CROSS_MERCHANT_ACCESS, severity=Severity.HIGH, source=actor_id,
            merchant_id=merchant.public_id,
            summary=(f"{who} {actor_id} of {merchant.name} ({merchant.public_id}) asked for "
                     f"{attempts} records of other merchants within "
                     f"{rules['CROSS_MERCHANT_ALERT_WINDOW_MINUTES']} minutes."),
            details={"attempts": attempts, "last_target": target_id,
                     "actor_type": actor_type})
    return True
