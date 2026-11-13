"""Keyed hashes for screening keys, so screening never stores a readable email or IP.

HMAC-SHA256 with a key derived from the card fingerprint secret (domain-separated, so an
email hash can never equal a card fingerprint). Card fingerprints come from the vault.
"""
import hashlib
import hmac

from django.conf import settings


def _keyed(domain: str, value: str) -> str:
    key = hmac.new(settings.CARD_FINGERPRINT_KEY.encode(), domain.encode(),
                   hashlib.sha256).digest()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()


def email_hash(email: str | None) -> str:
    return _keyed("risk-email-v1", email.strip().lower()) if email else ""


def ip_hash(ip: str | None) -> str:
    return _keyed("risk-ip-v1", ip.strip()) if ip else ""
