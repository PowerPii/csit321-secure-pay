"""HMAC-SHA256 signatures for webhooks and signed API responses.

Header format: `SecurePay-Signature: t=<unix seconds>,v1=<hex hmac of "t.body">`.
The demo merchant keeps its own copy of `verify` so the two are tested independently.
"""
import hashlib
import hmac
import time

HEADER = "SecurePay-Signature"


def sign(body: bytes, secret: str, timestamp: int | None = None) -> str:
    ts = int(time.time()) if timestamp is None else timestamp
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def verify(body: bytes, header: str, secret: str, tolerance: int = 300, now: int | None = None) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts = int(parts["t"])
        given = parts["v1"]
    except (KeyError, ValueError):
        return False
    now = int(time.time()) if now is None else now
    if abs(now - ts) > tolerance:
        return False
    expected = sign(body, secret, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, given)
