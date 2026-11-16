"""Data encryption keys and their rotation (FR-ADM-14, NFR-ENC-03; UC-45).

    encrypt(purpose, plaintext, aad) -> str     with the purpose's active key
    decrypt(purpose, stored, aad)    -> bytes   with whichever key the value names
    rotate(purpose, staff_id)        -> DataKey new active key; the old one is decrypt-only
    report()                         -> list[dict] every key with its age (the key report)

Envelope encryption: each value is encrypted with a random 256-bit data key (AES-256-GCM),
and the data key is stored in `DataKey` wrapped by the purpose's master key, a Compose
secret that never enters the database. Stored values look like `k1.<key_id>.<base64>` so
the right key is found after any number of rotations. Values written before key rotation
existed (`v1.` vault values and plain Fernet tokens) still decrypt with the master key, so a
rotation never makes existing data unreadable (NFR-ENC-03 acceptance: 0 failed decryptions).

The first value encrypted for a purpose creates its first data key, so key ages count from
deployment. Unwrapped keys are cached per process (a key never changes once made); which key
is active is cached for ACTIVE_CACHE_SECONDS, and an old key keeps decrypting meanwhile.
"""
import base64
import os
import time
from datetime import timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.common.ids import new_id
from apps.security.models import DataKey

PREFIX = "k1."
NONCE_BYTES = 12
ACTIVE_CACHE_SECONDS = 5

_unwrapped: dict[str, bytes] = {}
_active: dict[str, tuple[float, str]] = {}


def master_key(purpose: str) -> bytes:
    """The Compose secret for this purpose: 32 bytes, URL-safe base64 (a Fernet key works)."""
    value = (settings.VAULT_ENCRYPTION_KEY if purpose == DataKey.Purpose.VAULT
             else settings.FIELD_ENCRYPTION_KEY)
    key = base64.urlsafe_b64decode(value)
    if len(key) != 32:
        raise ValueError(f"the {purpose} master key must decode to 32 bytes (AES-256)")
    return key


def _wrap(purpose: str, key_id: str, raw: bytes) -> str:
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(master_key(purpose)).encrypt(nonce, raw, f"{purpose}:{key_id}".encode())
    return base64.b64encode(nonce + sealed).decode()


def _unwrap(key: DataKey) -> bytes:
    raw = base64.b64decode(key.wrapped_key)
    return AESGCM(master_key(key.purpose)).decrypt(
        raw[:NONCE_BYTES], raw[NONCE_BYTES:], f"{key.purpose}:{key.key_id}".encode())


def _new_key(purpose: str, created_by: str = "") -> DataKey:
    key = DataKey(purpose=purpose, created_by=created_by, key_id=new_id("dk"))
    raw = os.urandom(32)
    key.wrapped_key = _wrap(purpose, key.key_id, raw)
    key.save(force_insert=True)
    _unwrapped[key.key_id] = raw
    return key


def key_bytes(key_id: str) -> bytes:
    if key_id not in _unwrapped:
        _unwrapped[key_id] = _unwrap(DataKey.objects.get(key_id=key_id))
    return _unwrapped[key_id]


def active_key_id(purpose: str) -> str:
    cached = _active.get(purpose)
    if cached and cached[0] > time.monotonic():
        return cached[1]
    key = DataKey.objects.filter(purpose=purpose, status=DataKey.Status.ACTIVE).first()
    if key is None:
        try:
            with transaction.atomic():
                key = _new_key(purpose)
        except IntegrityError:  # another process made the first key at the same moment
            key = DataKey.objects.get(purpose=purpose, status=DataKey.Status.ACTIVE)
    _active[purpose] = (time.monotonic() + ACTIVE_CACHE_SECONDS, key.key_id)
    return key.key_id


def forget() -> None:
    """Drop the cached active key IDs (after a rotation, and in tests)."""
    _active.clear()


def forget_all() -> None:
    """Also drop unwrapped keys (tests, whose rows roll back)."""
    _active.clear()
    _unwrapped.clear()


def encrypt(purpose: str, plaintext: bytes, aad: bytes = b"") -> str:
    key_id = active_key_id(purpose)
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(key_bytes(key_id)).encrypt(nonce, plaintext, aad or None)
    return f"{PREFIX}{key_id}.{base64.b64encode(nonce + sealed).decode()}"


def is_keyring_value(stored: str) -> bool:
    return stored.startswith(PREFIX)


def key_id_of(stored: str) -> str:
    return stored[len(PREFIX):].split(".", 1)[0]


def decrypt(stored: str, aad: bytes = b"") -> bytes:
    if not is_keyring_value(stored):
        raise ValueError("not a keyring value")
    key_id, _, body = stored[len(PREFIX):].partition(".")
    raw = base64.b64decode(body)
    return AESGCM(key_bytes(key_id)).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad or None)


def rotate(purpose: str, staff_id: str) -> tuple[DataKey, DataKey | None]:
    """Make a new active key; the old one stays for decryption only. Returns (new, old)."""
    if purpose not in DataKey.Purpose.values:
        raise ValueError(purpose)
    now = timezone.now()
    with transaction.atomic():
        old = (DataKey.objects.select_for_update()
               .filter(purpose=purpose, status=DataKey.Status.ACTIVE).first())
        if old is not None:
            old.status, old.retired_at, old.retired_by = DataKey.Status.DECRYPT_ONLY, now, staff_id
            old.save(update_fields=["status", "retired_at", "retired_by"])
        new = _new_key(purpose, staff_id)
    forget()
    return new, old


def max_age_days() -> int:
    return settings.GATEWAY_RULES["KEY_MAX_AGE_DAYS"]


def age_days(key: DataKey, now=None) -> int:
    return ((now or timezone.now()) - key.created_at).days


def report(now=None) -> list[dict]:
    """The key report (NFR-ENC-03): every data key, newest first per purpose. `overdue`
    marks an active key older than KEY_MAX_AGE_DAYS; `due_soon` one past KEY_WARNING_DAYS."""
    now = now or timezone.now()
    for purpose in DataKey.Purpose.values:
        active_key_id(purpose)  # a fresh database shows its first keys, not an empty report
    out = []
    for key in DataKey.objects.order_by("purpose", "-created_at"):
        age = age_days(key, now)
        active = key.status == DataKey.Status.ACTIVE
        out.append({
            "id": key.key_id,
            "purpose": key.purpose,
            "purpose_label": DataKey.Purpose(key.purpose).label,
            "status": key.status,
            "created_at": key.created_at,
            "created_by": key.created_by or None,
            "retired_at": key.retired_at,
            "age_days": age,
            "rotate_by": key.created_at + timedelta(days=max_age_days())
            if active else None,
            "overdue": active and age >= max_age_days(),
            "due_soon": active and age >= settings.GATEWAY_RULES["KEY_WARNING_DAYS"],
        })
    return out


def overdue_keys(now=None) -> list[DataKey]:
    cutoff = (now or timezone.now()) - timedelta(days=max_age_days())
    return list(DataKey.objects.filter(status=DataKey.Status.ACTIVE, created_at__lte=cutoff))
