"""Append-only audit trail (AS 10, FR-TXN-16, NFR-AUD).

Every sign-in and every state change writes one row. Rows are never updated or deleted:
the model refuses it, and a database trigger (migration 0002) refuses it for raw SQL too.
Identifiers are stored as strings rather than foreign keys, so deleting or changing other
records can never cascade into the audit trail. Never put card data or secrets in `details`.
"""
from django.db import models


class AuditEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("audit events are append-only")

    def delete(self):
        raise PermissionError("audit events are append-only")


class AuditEvent(models.Model):
    class ActorType(models.TextChoices):
        MERCHANT_API = "merchant_api"  # actor_id is the API key's public ID
        STAFF = "staff"
        CUSTOMER = "customer"
        SYSTEM = "system"  # worker, reconciliation, management commands

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.CharField(max_length=64, blank=True)
    merchant_id = models.CharField(max_length=32, blank=True, db_index=True)  # mer_...
    action = models.CharField(max_length=64)  # e.g. payment.created
    target_type = models.CharField(max_length=32, blank=True)
    target_id = models.CharField(max_length=32, blank=True, db_index=True)
    request_id = models.CharField(max_length=32, blank=True, db_index=True)  # req_...
    # FR-TXN-16: the payment this entry belongs to (pay_...), so every entry about a payment,
    # its operations and its refunds is found by one ID. Filled in by `record`.
    correlation_id = models.CharField(max_length=32, blank=True, db_index=True)
    details = models.JSONField(default=dict, blank=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]

    def __str__(self):
        return f"{self.occurred_at:%Y-%m-%d %H:%M:%S} {self.action} {self.target_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("audit events are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("audit events are append-only")


class AuditSeal(models.Model):
    """The hash chain over audit entries (NFR-INT-02).

    The worker seals entries in ID order a short while after they are written: each seal
    holds an HMAC of the entry's content and of the previous seal, so an entry edited,
    deleted or moved directly in the database no longer matches, and removing a seal breaks
    the chain. The HMAC key is derived from a Compose secret, so the chain cannot be rebuilt
    from the database alone. Append-only like the entries (trigger in migration 0004).
    """

    position = models.PositiveBigIntegerField(unique=True)  # 1, 2, 3 ... no gaps
    event_id = models.BigIntegerField(unique=True)  # AuditEvent.id (not a foreign key)
    previous_hash = models.CharField(max_length=64)
    entry_hash = models.CharField(max_length=64)
    sealed_at = models.DateTimeField(auto_now_add=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        ordering = ["position"]

    def __str__(self):
        return f"seal {self.position} -> event {self.event_id}"


def correlation_for(target_type: str, target_id: str, details: dict) -> str:
    """The payment an entry belongs to: the target itself, or `payment_id` in the details."""
    if target_type == "payment":
        return target_id
    payment_id = details.get("payment_id")
    if isinstance(payment_id, str) and payment_id.startswith("pay_"):
        return payment_id[:32]
    return ""


def record(action: str, *, actor_type: str, actor_id: str = "", merchant_id: str = "",
           target_type: str = "", target_id: str = "", request_id: str = "",
           details: dict | None = None, correlation_id: str = "") -> AuditEvent:
    from apps.common.logmask import mask_value

    details = mask_value(details or {})
    return AuditEvent.objects.create(
        action=action, actor_type=actor_type, actor_id=actor_id, merchant_id=merchant_id,
        target_type=target_type, target_id=target_id, request_id=request_id or "",
        correlation_id=correlation_id or correlation_for(target_type, target_id, details),
        details=details,
    )
