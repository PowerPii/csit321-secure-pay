"""Simulated verification (FR-CHK-05, FR-CHK-06, FR-CHK-18; screen C5).

One challenge per payment attempt. Only a keyed hash of the current code is stored; a new
code replaces the old one. Wrong codes are counted across codes, so asking for a new code
does not reset the 3 attempts.
"""
from django.db import models


class VerificationChallenge(models.Model):
    payment = models.OneToOneField("payments.Payment", on_delete=models.PROTECT,
                                   related_name="verification")
    code_hash = models.CharField(max_length=64)
    code_sent_at = models.DateTimeField()
    code_expires_at = models.DateTimeField()
    codes_sent = models.PositiveSmallIntegerField(default=1)
    wrong_attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"verification for payment {self.payment_id}"
