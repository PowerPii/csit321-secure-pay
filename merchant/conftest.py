"""Shared fixtures for the demo shop: a stand-in for the SecurePay merchant API."""
import json

import httpx
import pytest

SECRET = "whsec_test_secret"
KEY = "sp_test_" + "k" * 40


def sign(body: bytes, secret: str, ts: int | None = None) -> str:
    import hashlib
    import hmac
    import time

    ts = int(time.time()) if ts is None else ts
    mac = hmac.new(secret.encode(), f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


class FakeGateway:
    """Answers POST /v1/payments and GET /v1/payments/{id} like the gateway.

    `next_status` is what a GET reports; `mode` can be "down", "unsigned", "bad_signature".
    """

    def __init__(self):
        self.calls = []
        self.payments = {}
        self.by_key = {}
        self.mode = "normal"
        self.next_status = "authorised"
        self.amount_override = None
        self.counter = 0
        self.settle_reply = None  # (status, body) for capture/cancel instead of success

    def payment(self, body, status="created", sequence=1):
        self.counter += 1
        pid = f"pay_{self.counter:024d}"
        return {"id": pid, "object": "payment", "reference": f"SP-AAAA-{self.counter:04d}",
                "order_reference": body["order_reference"], "status": status,
                "amount": body["amount"], "currency": "SGD", "sequence": sequence,
                "checkout_url": f"https://gateway.localhost/pay/cs_{self.counter:024d}"}

    def reply(self, status, data):
        raw = json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
        if self.mode != "unsigned":
            headers["SecurePay-Signature"] = sign(raw, "wrong" if self.mode == "bad_signature"
                                                  else SECRET)
        return httpx.Response(status, content=raw, headers=headers)

    def __call__(self, request):
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.path, body, dict(request.headers)))
        if self.mode == "down":
            raise httpx.ConnectError("down", request=request)
        assert request.headers["Authorization"] == f"Bearer {KEY}"
        if request.method == "POST" and request.url.path == "/v1/payments":
            key = request.headers["Idempotency-Key"]
            if key not in self.by_key:
                self.by_key[key] = self.payment(body)
                self.payments[self.by_key[key]["id"]] = (body, self.by_key[key])
            return self.reply(201, self.by_key[key])
        if request.method == "POST" and request.url.path.endswith("/refunds"):
            pid = request.url.path.split("/")[3]
            created = self.payments[pid][1]
            return self.reply(201, {"id": "rfd_" + "R" * 24, "object": "refund",
                                    "reference": "RF-AAAA-0001", "payment_id": pid,
                                    "payment_reference": created["reference"],
                                    "amount": body["amount"], "currency": "SGD",
                                    "status": "completed", "reason": body.get("reason"),
                                    "failure_reason": None})
        if request.method == "POST":  # /v1/payments/{id}/capture or /cancel
            _, _, _, pid, action = request.url.path.split("/")
            key = (action, request.headers["Idempotency-Key"])
            if key not in self.by_key:
                created = self.payments[pid][1]
                if self.settle_reply:
                    self.by_key[key] = self.settle_reply
                else:
                    status = "captured" if action == "capture" else "cancelled"
                    amount = (body or {}).get("amount", created["amount"])
                    self.by_key[key] = (200, {**created, "status": status, "sequence": 4,
                                              "checkout_url": None,
                                              "captured_amount": amount
                                              if action == "capture" else 0})
            return self.reply(*self.by_key[key])
        pid = request.url.path.rsplit("/", 1)[-1]
        body, created = self.payments[pid]
        data = {**created, "status": self.next_status, "sequence": 3, "checkout_url": None}
        if self.amount_override is not None:
            data["amount"] = self.amount_override
        return self.reply(200, data)


@pytest.fixture
def gateway(settings, monkeypatch):
    from apps.shop import securepay

    settings.SECUREPAY_API_KEY = KEY
    settings.SECUREPAY_SIGNING_SECRET = SECRET
    settings.SECUREPAY_API_URL = "https://gateway.localhost"
    settings.SHOP_BASE_URL = "https://shop.localhost"
    fake = FakeGateway()
    monkeypatch.setattr(securepay, "TRANSPORT", httpx.MockTransport(fake))
    return fake
