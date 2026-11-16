"""Encryption for secrets the gateway must be able to read back (merchant signing secrets,
queued email bodies).

New values use the field data key from the keyring (AES-256-GCM, apps/security/keyring.py),
so an administrator can rotate it (FR-ADM-14). Values from before key rotation are Fernet
tokens under `FIELD_ENCRYPTION_KEY` and still decrypt. API keys are not encrypted: only their
digest is stored, because the gateway never needs the key itself again (FR-MER-03).
"""
from cryptography.fernet import Fernet
from django.conf import settings

PURPOSE = "field"


def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY)


def encrypt(plaintext: str) -> str:
    from apps.security import keyring

    return keyring.encrypt(PURPOSE, plaintext.encode())


def encrypt_legacy(plaintext: str) -> str:
    """The pre-rotation format, kept so tests can prove such values still open."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    from apps.security import keyring

    if keyring.is_keyring_value(token):
        return keyring.decrypt(token).decode()
    return _fernet().decrypt(token.encode()).decode()
