"""Card data held between card entry and submission (architecture section 11).

The number and security code are stored only as Fernet ciphertext under VAULT_ENCRYPTION_KEY,
in the vault database role's own schema. The row is deleted when the payment is submitted
(Fifa's decision: card data deleted after submit), or when the checkout session ends unused.
"""
from django.db import models


class StoredCard(models.Model):
    token = models.CharField(max_length=32, unique=True, editable=False)  # tok_...
    ciphertext = models.TextField(editable=False)  # Fernet({number, cvc})
    brand = models.CharField(max_length=16)
    last4 = models.CharField(max_length=4)
    expiry_month = models.PositiveSmallIntegerField()
    expiry_year = models.PositiveSmallIntegerField()
    fingerprint = models.CharField(max_length=64)  # keyed HMAC, see fingerprint.py
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    def __str__(self):
        return f"{self.token} {self.brand} {self.last4}"
