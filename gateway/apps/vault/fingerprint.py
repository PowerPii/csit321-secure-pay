"""Card fingerprint: a stable, non-reversible key for prior-activity features.

HMAC-SHA256 of the normalised card number with a server secret, so the same card gives
the same fingerprint without the gateway keeping a readable number outside the vault.
"""
import hashlib
import hmac

from django.conf import settings


def normalise_pan(pan: str) -> str:
    digits = "".join(ch for ch in pan if ch.isdigit())
    if not 12 <= len(digits) <= 19:
        raise ValueError("card number must have 12 to 19 digits")
    return digits


def card_fingerprint(pan: str, key: str | None = None) -> str:
    key = key or settings.CARD_FINGERPRINT_KEY
    return hmac.new(key.encode(), normalise_pan(pan).encode(), hashlib.sha256).hexdigest()


def last4(pan: str) -> str:
    return normalise_pan(pan)[-4:]
