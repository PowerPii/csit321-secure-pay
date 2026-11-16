"""Staff accounts: role, merchant and sign-in lockout (FR-ACC-14 to FR-ACC-16).

A staff member is a Django user (email as username) with one `StaffAccount`. Customer
accounts live in apps.customers and are not Django users.

Roles (URS 3.3, access control matrix):
* merchant_operator: one merchant's payments; capture, cancel and refund them.
* fraud_analyst: every merchant's flagged payments, read-only; records findings.
* administrator: every merchant read-only, merchant approval, audit log, operation re-checks.

The backend is the only authority: every staff view checks role and merchant (FR-ACC-16).
"""
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.common.ids import new_id


class Role(models.TextChoices):
    MERCHANT_OPERATOR = "merchant_operator", "Merchant operator"
    FRAUD_ANALYST = "fraud_analyst", "Fraud analyst"
    ADMINISTRATOR = "administrator", "Administrator"


class StaffAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        SUSPENDED = "suspended"  # can be reinstated
        DEACTIVATED = "deactivated"  # permanent; the history stays

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # stf_...
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name="staff_account")
    role = models.CharField(max_length=24, choices=Role.choices)
    # Only merchant operators belong to a merchant; the others see every merchant.
    merchant = models.ForeignKey("merchants.Merchant", on_delete=models.PROTECT, null=True,
                                 blank=True, related_name="staff")
    # Lockout (FR-ACC-15): wrong passwords and wrong TOTP codes since the last success.
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_sign_in_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # FR-ADM-02: suspended or deactivated by an administrator, with a reason. The Django user
    # is made inactive at the same time, which ends its sessions on their next request.
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    status_reason = models.CharField(max_length=200, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=["active", "suspended", "deactivated"]),
                name="staff_status_valid"),
            models.CheckConstraint(
                condition=Q(role__in=[r.value for r in Role]), name="staff_role_valid"),
            models.CheckConstraint(
                condition=(Q(role="merchant_operator", merchant__isnull=False)
                           | (~Q(role="merchant_operator") & Q(merchant__isnull=True))),
                name="staff_merchant_only_for_operators",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} ({self.role})"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("stf")
        super().save(*args, **kwargs)

    @property
    def email(self) -> str:
        return self.user.email

    @property
    def display_name(self) -> str:
        return self.user.get_full_name() or self.user.email

    @property
    def is_operator(self) -> bool:
        return self.role == Role.MERCHANT_OPERATOR

    @property
    def is_analyst(self) -> bool:
        return self.role == Role.FRAUD_ANALYST

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMINISTRATOR

    def is_locked(self, now=None) -> bool:
        return self.locked_until is not None and (now or timezone.now()) < self.locked_until

    def lock_seconds_left(self, now=None) -> int:
        if not self.is_locked(now):
            return 0
        return max(1, int((self.locked_until - (now or timezone.now())).total_seconds()))

    @staticmethod
    def lock_duration() -> timedelta:
        return timedelta(minutes=settings.GATEWAY_RULES["STAFF_LOCKOUT_MINUTES"])


class AccountToken(models.Model):
    """A one-time link token: password reset (FR-ACC-07) or email verification (FR-MER-01).

    The token is 32 random bytes that appear only in the emailed link; the database keeps its
    SHA-256 digest (API-CONTRACT.md section 9). A token works once and until `expires_at`; a
    new token for the same user and purpose withdraws the earlier ones.
    """

    class Purpose(models.TextChoices):
        PASSWORD_RESET = "password_reset"  # nosec B105
        EMAIL_VERIFICATION = "email_verification"

    # Staff and merchant registrations are Django users; customers (sprint 11) are not.
    # Exactly one of the two is set.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="account_tokens", null=True, blank=True)
    customer = models.ForeignKey("customers.CustomerAccount", on_delete=models.CASCADE,
                                 related_name="account_tokens", null=True, blank=True)
    purpose = models.CharField(max_length=24, choices=Purpose.choices)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    # Set when the token is used or withdrawn by a newer one; either way it no longer works.
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "purpose", "created_at"]),
                   models.Index(fields=["customer", "purpose", "created_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(Q(user__isnull=False, customer__isnull=True)
                           | Q(user__isnull=True, customer__isnull=False)),
                name="account_token_one_owner"),
            models.CheckConstraint(
                condition=Q(purpose__in=["password_reset", "email_verification"]),
                name="account_token_purpose_valid"),
        ]

    def __str__(self):
        owner = f"user {self.user_id}" if self.user_id else f"customer {self.customer_id}"
        return f"{self.purpose} for {owner}"
