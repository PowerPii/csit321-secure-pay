"""Products, orders and the SecurePay payments made for them.

The shop never sees card data. It creates a payment with its API key, sends the customer
to SecurePay's hosted checkout, and marks an order paid only after a signed answer from
the gateway says the payment is authorised (API-CONTRACT.md section 3, UC-27).
"""
import uuid

from django.db import models


class Product(models.Model):
    """A catalogue item of Volt & Co., the fictional store the demo shop plays."""

    CATEGORIES = [("audio", "Audio"), ("computing", "Computing"), ("accessories", "Accessories")]

    sku = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=80)
    price_cents = models.PositiveIntegerField()
    position = models.PositiveSmallIntegerField(default=0)
    category = models.CharField(max_length=16, choices=CATEGORIES, default="accessories")
    blurb = models.CharField(max_length=140, blank=True)  # one line on cards
    description = models.TextField(blank=True)
    details = models.TextField(blank=True)  # one spec per line
    art = models.CharField(max_length=24, blank=True)  # illustration key (templatetags/shop.py)
    badge = models.CharField(max_length=16, blank=True)  # "New", "Bestseller"
    stock = models.PositiveSmallIntegerField(default=25)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def detail_lines(self) -> list[str]:
        return [line.strip() for line in self.details.splitlines() if line.strip()]


class Order(models.Model):
    session_key = models.CharField(max_length=64, db_index=True)  # the browser that ordered
    email = models.EmailField(max_length=254)
    full_name = models.CharField(max_length=120)
    delivery_address = models.CharField(max_length=300)
    total_cents = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.reference} {self.total_cents}"

    @property
    def number(self) -> int:
        return 1000 + self.pk

    @property
    def reference(self) -> str:
        """Sent to SecurePay as order_reference."""
        return f"ORD-{self.number}"

    @property
    def latest_attempt(self):
        return self.attempts.order_by("-id").first()

    def line_items(self) -> list[dict]:
        """Shown on SecurePay's checkout page; they add up to total_cents."""
        return [{"name": line.name, "quantity": line.quantity,
                 "unit_amount": line.unit_price_cents} for line in self.lines.all()]

    def description(self) -> str:
        text = ", ".join(f"{line.name} × {line.quantity}" for line in self.lines.all())
        return text if len(text) <= 200 else text[:197] + "..."


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    sku = models.CharField(max_length=32)
    name = models.CharField(max_length=80)
    unit_price_cents = models.PositiveIntegerField()
    quantity = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["id"]

    @property
    def total_cents(self) -> int:
        return self.unit_price_cents * self.quantity


class PaymentAttempt(models.Model):
    """One SecurePay payment for an order. A new attempt after a decline gets a new key."""

    # Statuses after which the order is paid, waiting, or needs a new attempt.
    PAID = frozenset({"authorised", "captured"})
    WAITING = frozenset({"screening", "verification_required", "processing", "unresolved"})
    FAILED = frozenset({"declined", "blocked", "cancelled", "expired"})

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="attempts")
    # Saved before calling the gateway, so a retry after a lost reply reuses it.
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment_id = models.CharField(max_length=32, blank=True, db_index=True)  # pay_...
    reference = models.CharField(max_length=12, blank=True)  # SP-XXXX-XXXX
    status = models.CharField(max_length=24, blank=True)  # last signed status seen
    sequence = models.PositiveIntegerField(default=0)  # ignore anything older (section 6)
    checkout_url = models.URLField(max_length=2048, blank=True)
    # Keys for capture and cancel, saved before the call so a retry after a lost reply
    # cannot capture twice (API-CONTRACT.md section 5).
    capture_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    cancel_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    captured_amount = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.payment_id or 'not created'} {self.status}"
