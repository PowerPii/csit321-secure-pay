"""Fault rules for recovery tests (SIMULATOR-CONTRACT.md section 8, FR-SIM-02).

A rule says which operations it matches (every given field must match; none given matches
all), what to do to them, and how many more times (`remaining`, or null until removed).
Rules exist only through the test-control API, which is off unless SIM_TEST_CONTROLS=1.
"""
from django.db import models

from apps.common.http import rfc3339
from apps.common.ids import new_id

MATCH_FIELDS = ("operation_type", "payment_id", "merchant_id", "card_last4")


class FaultRule(models.Model):
    class Action(models.TextChoices):
        DROP_REQUEST = "drop_request"
        DELAY_REQUEST = "delay_request"
        DROP_RESPONSE = "drop_response"
        DELAY_RESPONSE = "delay_response"
        FAIL_STATUS_QUERY = "fail_status_query"
        NOTIFY = "notify"

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # flt_...
    match = models.JSONField(default=dict)
    action = models.CharField(max_length=24, choices=Action.choices)
    delay_ms = models.PositiveIntegerField(null=True, blank=True)
    copies = models.PositiveSmallIntegerField(default=1)
    remaining = models.PositiveIntegerField(null=True, blank=True)  # null = until removed
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.public_id} {self.action} {self.match} x{self.remaining}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("flt")
        super().save(*args, **kwargs)

    def matches(self, context: dict) -> bool:
        return all(context.get(name) == value for name, value in self.match.items())

    def to_dict(self) -> dict:
        data = {"id": self.public_id, "match": self.match, "action": self.action,
                "remaining": self.remaining, "created_at": rfc3339(self.created_at)}
        if self.delay_ms is not None:
            data["delay_ms"] = self.delay_ms
        if self.action == self.Action.NOTIFY:
            data["copies"] = self.copies
        return data
