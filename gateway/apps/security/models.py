"""Security alerts for administrators (FR-ADM-08, UC-40; NFR-PER-03).

A security alert says that something that looks like an attack happened: an account locked
after repeated failed sign-ins, repeated attempts to read another merchant's records
(FR-MER-09, UC-22), and the later checks that report through the same channel. Repeats of
the same event from the same source are grouped into one open alert with a count, so a
burst does not flood the dashboard or the administrators' inboxes. Alerts are never deleted;
an administrator resolves one with a note.
"""
from django.db import models
from django.db.models import Q

from apps.common.ids import new_id


class Severity(models.TextChoices):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AlertKind(models.TextChoices):
    STAFF_LOCKED = "staff_locked", "Staff account locked"
    CUSTOMER_LOCKED = "customer_locked", "Customer account locked"
    CROSS_MERCHANT_ACCESS = "cross_merchant_access", "Repeated cross-merchant access"


class SecurityAlert(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # sal_...
    kind = models.CharField(max_length=32, choices=AlertKind.choices)
    severity = models.CharField(max_length=8, choices=Severity.choices)
    # Who or what caused it: a staff, customer or API key ID, or "ip:203.0.113.5". Repeats
    # with the same kind and source are grouped.
    source = models.CharField(max_length=80)
    merchant_id = models.CharField(max_length=32, blank=True)  # mer_..., when there is one
    summary = models.CharField(max_length=300)
    details = models.JSONField(default=dict, blank=True)  # the latest event's details
    count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    resolved_by = models.ForeignKey("accounts.StaffAccount", on_delete=models.PROTECT,
                                    null=True, blank=True, related_name="+")
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(max_length=1000, blank=True)

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [models.Index(fields=["kind", "source", "status"])]
        constraints = [
            models.CheckConstraint(condition=Q(severity__in=["low", "medium", "high"]),
                                   name="security_alert_severity_valid"),
            models.CheckConstraint(
                condition=(Q(status="open", resolved_at__isnull=True)
                           | Q(status="resolved", resolved_at__isnull=False)),
                name="security_alert_resolution_consistent"),
        ]

    def __str__(self):
        return f"{self.public_id} {self.kind} x{self.count} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("sal")
        super().save(*args, **kwargs)
