"""Transactional outbox for webhook events (API-CONTRACT.md sections 6 and 7, FR-TXN-06/07).

An OutboxEvent is written in the same database transaction as the status change it
describes. The worker (sprint 3) delivers it; delivery results never change a payment.
"""
from django.db import models
from django.db.models import Q

from apps.common.ids import new_id
from apps.merchants.models import Merchant
from apps.payments.models import Payment


class EventType(models.TextChoices):
    PAYMENT_VERIFICATION_REQUIRED = "payment.verification_required"
    PAYMENT_PROCESSING = "payment.processing"
    PAYMENT_AUTHORISED = "payment.authorised"
    PAYMENT_DECLINED = "payment.declined"
    PAYMENT_BLOCKED = "payment.blocked"
    PAYMENT_UNRESOLVED = "payment.unresolved"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_CANCELLED = "payment.cancelled"
    PAYMENT_EXPIRED = "payment.expired"
    REFUND_COMPLETED = "refund.completed"
    REFUND_FAILED = "refund.failed"
    REFUND_UNRESOLVED = "refund.unresolved"


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"  # waiting for its first or next attempt
        DELIVERED = "delivered"
        UNDELIVERED = "undelivered"  # retry window ended; kept, shown on the dashboard

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # evt_...
    merchant = models.ForeignKey(Merchant, on_delete=models.PROTECT, related_name="events")
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="events")
    type = models.CharField(max_length=40, choices=EventType.choices)
    sequence = models.PositiveIntegerField()
    # The event envelope as the merchant will receive it. Signed fresh on every attempt.
    payload = models.JSONField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    first_failed_at = models.DateTimeField(null=True, blank=True)  # starts the 72 h window
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField()  # when the status change was committed

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["payment", "sequence"],
                                    name="one_event_per_payment_sequence"),
        ]
        indexes = [
            models.Index(fields=["next_attempt_at"], condition=Q(status="pending"),
                         name="outbox_due_idx"),
        ]

    def __str__(self):
        return f"{self.public_id} {self.type} #{self.sequence} {self.status}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("evt")
        super().save(*args, **kwargs)
