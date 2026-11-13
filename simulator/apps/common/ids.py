"""Simulator identifiers (SIMULATOR-CONTRACT.md section 2): prefix + 24 base62 characters."""
import secrets
import string

BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase


def new_id(prefix: str) -> str:
    return f"{prefix}_" + "".join(secrets.choice(BASE62) for _ in range(24))
