"""Guest status check with an emailed one-time code (API-CONTRACT.md section 8, screen C9).

FR-ACC-05: the reference alone never shows a payment; the guest also gives the checkout
email and then a code emailed to it. FR-ACC-06: the reply is the same whether or not they
match, and 3 wrong codes lock the check for that reference and email for 15 minutes.

Reference + email pairs and IP addresses are stored only as keyed hashes (`pair_key`,
`ip_key`), and codes and session tokens only as keyed hashes, so the tables never hold a
usable code or a list of who checked what.
"""
from django.db import models

from apps.common.ids import new_id


class StatusChallenge(models.Model):
    """One code request. A request that matched nothing gets a challenge too (payment null),
    whose code is random and never sent, so it behaves exactly like a real one."""

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # gsc_...
    pair_key = models.CharField(max_length=64, db_index=True)
    ip_key = models.CharField(max_length=64, db_index=True)
    payment = models.ForeignKey("payments.Payment", null=True, blank=True,
                                on_delete=models.CASCADE, related_name="status_challenges")
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    replaced_at = models.DateTimeField(null=True, blank=True)  # a newer code for the pair
    used_at = models.DateTimeField(null=True, blank=True)  # single use
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.public_id} {'match' if self.payment_id else 'no match'}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("gsc")
        super().save(*args, **kwargs)


class StatusLock(models.Model):
    """Wrong codes for a reference + email pair, counted across codes (like checkout
    verification), and the 15-minute lock after the third."""

    pair_key = models.CharField(max_length=64, unique=True)
    wrong_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.pair_key[:8]} wrong={self.wrong_attempts} until={self.locked_until}"


class StatusSession(models.Model):
    """The `sp_guest_status` cookie: one payment, read-only, 15 minutes."""

    token_hash = models.CharField(max_length=64, unique=True)
    payment = models.ForeignKey("payments.Payment", on_delete=models.CASCADE,
                                related_name="status_sessions")
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"status session for payment {self.payment_id}"
