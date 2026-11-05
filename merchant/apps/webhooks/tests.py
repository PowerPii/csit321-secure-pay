import hashlib
import hmac

from apps.webhooks.signing import verify


def header(body, secret, ts):
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def test_valid_signature():
    assert verify(b"{}", header(b"{}", "s", 100), "s", now=100)


def test_rejects_tampering_and_replay():
    assert not verify(b"{ }", header(b"{}", "s", 100), "s", now=100)
    assert not verify(b"{}", header(b"{}", "s", 100), "s", now=1000)
