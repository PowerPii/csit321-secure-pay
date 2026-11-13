"""Fraud review cases and findings (D6, D6b; FR-FRD-05, FR-FRD-07).

A case is a flagged screening decision (Block or Verify). Its row is created the first time
an analyst assigns it or records a finding; until then the case is open and unassigned.
Rule: a finding never changes the payment or its screening outcome.
"""
from django.db import models
from django.db.models import Q


class ReviewCase(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    class Finding(models.TextChoices):
        CONFIRMED_FRAUD = "confirmed_fraud", "Confirmed fraud"
        FALSE_POSITIVE = "false_positive", "False positive"
        INCONCLUSIVE = "inconclusive", "Inconclusive"

    screening = models.OneToOneField("risk.ScreeningEvent", on_delete=models.PROTECT,
                                     related_name="review")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    assigned_to = models.ForeignKey("accounts.StaffAccount", on_delete=models.PROTECT,
                                    null=True, blank=True, related_name="review_cases")
    finding = models.CharField(max_length=16, choices=Finding.choices, blank=True)
    notes = models.TextField(max_length=1000, blank=True)
    reviewed_by = models.ForeignKey("accounts.StaffAccount", on_delete=models.PROTECT,
                                    null=True, blank=True, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(status__in=["open", "closed"]),
                                   name="review_status_valid"),
            models.CheckConstraint(condition=Q(status="open") | ~Q(finding=""),
                                   name="review_closed_has_finding"),
        ]

    def __str__(self):
        return f"{self.screening_id} {self.status} {self.finding}"
