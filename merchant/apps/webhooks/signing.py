"""The shop's own webhook verifier (deliberately not imported from the gateway).

Header: `SecurePay-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "t.body">`.
After verifying, the shop deduplicates by event ID, ignores events with an older
sequence number, and confirms with GET /v1/payments/{id} before marking an order paid.
"""
import hashlib
import hmac
import time


def verify(body: bytes, header: str, secret: str, tolerance: int = 300, now: int | None = None) -> bool:
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        ts, given = int(parts["t"]), parts["v1"]
    except (KeyError, ValueError):
        return False
    if abs((int(time.time()) if now is None else now) - ts) > tolerance:
        return False
    expected = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, given)
