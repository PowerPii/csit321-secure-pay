"""Public identifiers (API-CONTRACT.md section 1).

Opaque, prefixed, 24 base62 characters after the prefix, for example `pay_...`. Database
primary keys stay internal; only these IDs leave the gateway.
"""
import secrets
import string

BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
# Customer-facing references avoid characters that are easy to misread (0/O, 1/I).
REFERENCE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def random_base62(length: int) -> str:
    return "".join(secrets.choice(BASE62) for _ in range(length))


def new_id(prefix: str) -> str:
    """`new_id("pay")` -> `pay_` + 24 base62 characters (about 143 bits)."""
    return f"{prefix}_{random_base62(24)}"


def new_reference(prefix: str) -> str:
    """`new_reference("SP")` -> `SP-XXXX-XXXX` (FR-CHK-08)."""
    a = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(4))
    b = "".join(secrets.choice(REFERENCE_ALPHABET) for _ in range(4))
    return f"{prefix}-{a}-{b}"
