"""Transactional outbox for webhook events (API-CONTRACT.md sections 6 and 7, FR-TXN-06/07).

An OutboxEvent is written in the same database transaction as the status change it
describes. The worker delivers it (apps/events/delivery.py); delivery results never change a
payment.
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
    # A manual resend (webhook log) starts a fresh retry schedule: attempts made
    # before it do not count towards WEBHOOK_RETRY_DELAYS_SECONDS.
    schedule_base = models.PositiveSmallIntegerField(default=0)
    resend_count = models.PositiveSmallIntegerField(default=0)
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


class WebhookAttempt(models.Model):
    """One delivery attempt of an event (API-CONTRACT.md section 7 "Recording", FR-TXN-07).

    Stores time, attempt number, HTTP status or error class, and duration, plus the first
    RESPONSE_EXCERPT_CHARS characters of the reply so the merchant can see why their endpoint
    refused it in the webhook log (control characters removed; never the request body).
    """

    RESPONSE_EXCERPT_CHARS = 300

    event = models.ForeignKey(OutboxEvent, on_delete=models.CASCADE, related_name="attempts")
    attempt_number = models.PositiveSmallIntegerField()
    started_at = models.DateTimeField()
    duration_ms = models.PositiveIntegerField()
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.CharField(max_length=64, blank=True)  # e.g. timeout, blocked_address
    succeeded = models.BooleanField(default=False)
    response_excerpt = models.CharField(max_length=300, blank=True)
    manual = models.BooleanField(default=False)  # the first attempt after a manual resend

    class Meta:
        ordering = ["event", "attempt_number"]
        constraints = [
            models.UniqueConstraint(fields=["event", "attempt_number"],
                                    name="one_attempt_per_number"),
        ]

    def __str__(self):
        return f"{self.event_id} #{self.attempt_number} {self.http_status or self.error}"


class OutboundEmail(models.Model):
    """An email, written in the transaction that decides to send it.

    Receipts (FR-CHK-15, UC-04) and guest status codes (API-CONTRACT.md section 8) go
    through here, so a failed send is retried and recorded (UC-04 alternative flow), and a
    guest status reply takes the same time whether or not a code is sent. The body is kept
    only as ciphertext (FIELD_ENCRYPTION_KEY) and is wiped once the email is sent, given up
    or past `discard_after`; a one-time code never stays in the database longer than that.
    Subjects are stored in plain text, so they never carry a code or a link.
    `public_id` is the stable message ID across retries (Message-ID and the provider's
    idempotency key), so a retry after a lost reply is not delivered twice.
    """

    class Kind(models.TextChoices):
        RECEIPT = "receipt"
        REFUND_RECEIPT = "refund_receipt"  # demo sprint 14: the customer sees money come back
        GUEST_STATUS_CODE = "guest_status_code"
        # Accounts (sprint 10): links that carry a one-time token, and notices to staff.
        PASSWORD_RESET = "password_reset"  # nosec B105
        EMAIL_VERIFICATION = "email_verification"
        ACCOUNT_NOTICE = "account_notice"
        # Codex re-audit (19 Nov 2026): every email goes through the outbox, so each one has a
        # recorded outcome and only the worker (which has outbound network) sends mail.
        VERIFICATION_CODE = "verification_code"  # checkout code (FR-CHK-06)
        SECURITY_NOTICE = "security_notice"  # staff lockout / backup code used (FR-ACC-15)

    class Status(models.TextChoices):
        PENDING = "pending"  # queued, or waiting to retry (attempt_count, last_error)
        SENT = "sent"  # accepted by the route's server: the provider, or the capture inbox
        FAILED = "failed"  # attempts used up or refused for good; kept, body wiped
        DISCARDED = "discarded"  # expired before it could be sent (a code or reset link)
        SUPPRESSED = "suppressed"  # real recipient with no permitted route; never sent

    class Route(models.TextChoices):
        CAPTURE = "capture"  # Mailpit, the demo inbox (made-up addresses only on servers)
        PROVIDER = "provider"  # the real mail provider (Resend)
        SUPPRESS = "suppress"  # not sent

    public_id = models.CharField(max_length=32, unique=True, editable=False)  # eml_...
    kind = models.CharField(max_length=24, choices=Kind.choices)
    # Empty for account emails (password reset, registration), which belong to no payment.
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="emails",
                                null=True, blank=True)
    to = models.EmailField(max_length=254)
    subject = models.CharField(max_length=200)
    body_encrypted = models.TextField(blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    discard_after = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=64, blank=True)  # error class only
    sent_at = models.DateTimeField(null=True, blank=True)
    route = models.CharField(max_length=16, choices=Route.choices, blank=True)
    # Set when a worker claims the row; completion only counts with the same token, so a
    # worker whose lease ran out cannot overwrite another's result.
    claim_token = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["next_attempt_at"], condition=Q(status="pending"),
                         name="email_due_idx"),
        ]

    def __str__(self):
        return f"{self.public_id} {self.kind} {self.status}"

    def save(self, *args, **kwargs):
        if not self.public_id:
            self.public_id = new_id("eml")
        super().save(*args, **kwargs)


class WorkerHeartbeat(models.Model):
    """When the worker loop last finished a pass (one row per worker name).

    The readiness check (/readyz) and demo_check read it, so an uptime monitor notices a
    stopped worker: payments still go through without it, but webhooks, emails and
    reconciliation quietly stop.
    """

    name = models.CharField(max_length=32, primary_key=True)
    seen_at = models.DateTimeField()

    def __str__(self):
        return f"{self.name} {self.seen_at:%Y-%m-%d %H:%M:%S}"
