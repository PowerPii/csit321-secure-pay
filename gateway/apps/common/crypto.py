"""Encryption for secrets the gateway must be able to read back (merchant signing secrets).

Uses Fernet (AES-128-CBC + HMAC-SHA256) with `FIELD_ENCRYPTION_KEY` from a Compose secret.
API keys are not encrypted: only their digest is stored, because the gateway never needs
the key itself again (FR-MER-03).
"""
from cryptography.fernet import Fernet
from django.conf import settings


def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
