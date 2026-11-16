"""Customer accounts (FR-ACC-01 to FR-ACC-04, FR-ACC-07, FR-ACC-08; screens C10 to C12).

An account is optional: guests still pay and check a payment with the emailed code (C9).
Customers are kept apart from staff on purpose. They are not Django users, so a customer can
never pass a staff check, and their session is our own `sp_customer` cookie, not Django's
session, so signing in on the account pages never touches a staff sign-in in the same
browser (FR-ACC-11 style separation).

The password is a Django password hash (Argon2). Session tokens are stored only as keyed
hashes, like the guest status sessions.
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.common.ids import new_id


class CustomerAccount(models.Model):
    public_id = models.CharField(max_length=32, unique=True, editable=False)  # cus_...
    email = models.EmailField(max_length=254, unique=True)  # stored lower case
    full_name = models.CharField(max_length=100)
    password = models.CharField(max_length=256)  # Django password hash
    is_active = models.BooleanField(default=True)
    # Lockout (FR-ACC-03): wrong passwords since the last success.
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_sign_in_at = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(null=True, blank=True)
    # FR-ACC-12: the privacy notice agreed to at sign-up, and when.
    privacy_notice_version = models.CharField(max_length=16, blank=True)
    privacy_consent_at = models.DateTimeField(null=True, blank=True)
    # FR-ACC-13: when the customer last corrected their details.
    details_changed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.public_id} {self.email}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("cus")
        super().save(*args, **kwargs)

    # For Django's UserAttributeSimilarityValidator (a password like the email is refused).
    @property
    def username(self) -> str:
        return self.email

    def is_locked(self, now=None) -> bool:
        return self.locked_until is not None and (now or timezone.now()) < self.locked_until

    def lock_seconds_left(self, now=None) -> int:
        if not self.is_locked(now):
            return 0
        return max(1, int((self.locked_until - (now or timezone.now())).total_seconds()))

    @staticmethod
    def lock_duration() -> timedelta:
        return timedelta(minutes=settings.GATEWAY_RULES["CUSTOMER_LOCKOUT_MINUTES"])


class CustomerSession(models.Model):
    """One signed-in browser. Ends after CUSTOMER_IDLE_MINUTES without a request, after
    CUSTOMER_SESSION_MAX_HOURS in any case, on sign-out, and on every password change."""

    token_hash = models.CharField(max_length=64, unique=True)
    customer = models.ForeignKey(CustomerAccount, on_delete=models.CASCADE,
                                 related_name="sessions")
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    expires_at = models.DateTimeField()  # the absolute limit
    # "Keep me signed in on this device": the cookie outlives the browser window. The idle
    # limit still applies.
    persistent = models.BooleanField(default=False)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["customer", "ended_at"])]

    def __str__(self):
        return f"session of {self.customer_id} ended={self.ended_at}"
