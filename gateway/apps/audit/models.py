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


def record(action: str, *, actor_type: str, actor_id: str = "", merchant_id: str = "",
           target_type: str = "", target_id: str = "", request_id: str = "",
           details: dict | None = None) -> AuditEvent:
    return AuditEvent.objects.create(
        action=action, actor_type=actor_type, actor_id=actor_id, merchant_id=merchant_id,
        target_type=target_type, target_id=target_id, request_id=request_id or "",
        details=details or {},
    )
