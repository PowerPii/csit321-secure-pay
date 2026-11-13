"""Webhook events the shop has accepted, so a repeat or replay is ignored (contract section 7).

Kept at least 7 days, longer than the gateway's 72-hour retry window plus room for a
manual replay, which keeps the original event ID.
"""
from django.db import models


class ReceivedEvent(models.Model):
    event_id = models.CharField(max_length=32, unique=True)  # evt_...
    type = models.CharField(max_length=40)
    payment_id = models.CharField(max_length=32, db_index=True)
    sequence = models.PositiveIntegerField()
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # applied: confirmed with GET and stored; stale: older than what we have;
    # unknown_payment: not one of our attempts.
    outcome = models.CharField(max_length=16)

    def __str__(self):
        return f"{self.event_id} {self.type} #{self.sequence} {self.outcome}"
