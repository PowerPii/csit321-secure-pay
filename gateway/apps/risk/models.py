"""Screening records and the seeded block / review lists (architecture section 7, FR-FRD-01).

`ScreeningEvent` is both the decision record an analyst reads (score, reasons, feature values,
model / rules / policy versions) and the history that prior-activity features count. There is
one per payment attempt, so a retried submission can never be counted twice.

Nothing here holds a card number or a readable email or IP address: cards are keyed by the
vault's fingerprint, emails and IPs by a keyed hash (apps.risk.hashing).
"""
from django.db import models
from django.db.models import Q

from apps.common.ids import new_id


class ScreeningOutcome(models.TextChoices):
    ALLOW = "allow"
    VERIFY = "verify"
    BLOCK = "block"
    NOT_SCREENED = "not_screened"  # screening unavailable, the attempt was blocked (FR-FRD-04)


class ScreeningEvent(models.Model):
    public_id = models.CharField(max_length=32, unique=True, editable=False)  # scr_...
    payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT,
                                   related_name="screening")
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT,
                                 related_name="+")
    occurred_at = models.DateTimeField()
    amount = models.PositiveIntegerField()

    # Keys for prior-activity counts (never the raw values).
    card_fingerprint = models.CharField(max_length=64, blank=True)
    email_hash = models.CharField(max_length=64, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    device_hash = models.CharField(max_length=64, blank=True)  # no device cookie yet

    # The decision.
    outcome = models.CharField(max_length=16, choices=ScreeningOutcome.choices)
    score = models.FloatField(null=True, blank=True)
    reasons = models.JSONField(default=list, blank=True)
    features = models.JSONField(default=dict, blank=True)
    model_version = models.CharField(max_length=64, blank=True)
    rules_version = models.CharField(max_length=32, blank=True)
    policy_version = models.CharField(max_length=32, blank=True)
    feature_schema_version = models.CharField(max_length=32, blank=True)
    elapsed_ms = models.FloatField(default=0)
    # Why screening was unavailable (exception class / timeout). Never customer data.
    error = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["card_fingerprint", "occurred_at"], name="screen_card_time"),
            models.Index(fields=["email_hash", "occurred_at"], name="screen_email_time"),
            models.Index(fields=["ip_hash", "occurred_at"], name="screen_ip_time"),
            models.Index(fields=["outcome", "-occurred_at"], name="screen_outcome_time"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(outcome__in=[o.value for o in ScreeningOutcome]),
                name="screening_outcome_valid",
            ),
        ]

    def __str__(self):
        return f"{self.public_id} {self.outcome}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("scr")
        super().save(*args, **kwargs)


class RiskListEntry(models.Model):
    """A card, email or IP on the block list or the review (verify) list.

    The MVP seeds these with `manage.py seed_risk_lists` (FR-FRD-06 to 09, the analyst UI for
    editing lists, come later). Values are stored the same way screening keys them.
    """

    class Kind(models.TextChoices):
        CARD = "card"  # vault card fingerprint
        EMAIL = "email"  # keyed hash of the lower-cased email
        IP = "ip"  # keyed hash of the IP address

    class Action(models.TextChoices):
        BLOCK = "block"
        VERIFY = "verify"

    kind = models.CharField(max_length=8, choices=Kind.choices)
    value_hash = models.CharField(max_length=64)
    action = models.CharField(max_length=8, choices=Action.choices)
    label = models.CharField(max_length=100, help_text="Why it is listed; shown to analysts.")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kind", "value_hash"], name="one_list_entry_per_value"),
        ]

    def __str__(self):
        return f"{self.kind} {self.action}: {self.label}"


class FraudAlert(models.Model):
    """One alert to fraud analysts for each flagged payment (FR-FRD-08, UC-51).

    Created in the checkout's transaction when screening blocks a payment or asks for a
    verification code. The one-to-one link to the decision record is what keeps an event from
    raising a second alert: a later step on the same payment (a wrong code, a retry of the same
    submission) finds the alert that is already there. Unscreened attempts (screening
    unavailable) are a security matter for administrators (UC-39, UC-40), not a fraud alert.
    """

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # fal_...
    screening = models.OneToOneField(ScreeningEvent, on_delete=models.PROTECT,
                                     related_name="alert")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.public_id} {self.screening_id}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("fal")
        super().save(*args, **kwargs)


class FraudAlertRead(models.Model):
    """When one staff member opened (or dismissed) an alert. Each analyst has their own
    unread list, so one analyst reading an alert does not hide it from the others."""

    alert = models.ForeignKey(FraudAlert, on_delete=models.CASCADE, related_name="reads")
    staff = models.ForeignKey("accounts.StaffAccount", on_delete=models.CASCADE,
                              related_name="+")
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["alert", "staff"], name="one_read_per_alert_staff"),
        ]
