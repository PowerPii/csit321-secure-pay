"""Shared fixtures for gateway tests."""
import json
import uuid
from pathlib import Path
from typing import ClassVar

import pytest
from django.core.cache import cache
from jsonschema import Draft202012Validator
from rest_framework.test import APIClient

from apps.merchants.models import ApiKey, Merchant

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


@pytest.fixture(autouse=True)
def _clear_throttle_cache():
    cache.clear()  # rate-limit counters must not leak between tests
    yield
    cache.clear()


def _validator(name):
    schema = json.loads((CONTRACTS / "schemas" / name).read_text())
    return Draft202012Validator(schema)


@pytest.fixture(scope="session")
def payment_schema():
    return _validator("payment.schema.json")


@pytest.fixture(scope="session")
def error_schema():
    return _validator("error.schema.json")


class MerchantClient(APIClient):
    """An API client authenticated as one merchant, with its key and signing secret."""

    def __init__(self, merchant, api_key, plaintext, secret):
        super().__init__()
        self.merchant, self.api_key, self.key, self.secret = merchant, api_key, plaintext, secret
        self.credentials(HTTP_AUTHORIZATION=f"Bearer {plaintext}")

    def create_payment(self, body=None, key=None, **extra):
        body = body if body is not None else valid_body()
        headers = {} if key is False else {"Idempotency-Key": key or str(uuid.uuid4())}
        return self.post("/v1/payments", body, format="json", headers=headers, **extra)


def valid_body(**overrides):
    body = {
        "amount": 4590,
        "currency": "SGD",
        "order_reference": "ORD-10042",
        "return_url": "https://shop.localhost/orders/ORD-10042/return",
        "customer_email": "alex@example.com",
    }
    body.update(overrides)
    return {k: v for k, v in body.items() if v is not ...}


@pytest.fixture
def make_merchant(db):
    def make(name="Demo Shop", status=Merchant.Status.ACTIVE, **fields):
        merchant = Merchant(name=name, status=status, **fields)
        secret = merchant.rotate_signing_secret()
        merchant.save()
        api_key, plaintext = ApiKey.issue(merchant)
        return MerchantClient(merchant, api_key, plaintext, secret)

    return make


@pytest.fixture
def shop(make_merchant):
    return make_merchant()


@pytest.fixture
def other_shop(make_merchant):
    return make_merchant(name="Other Shop")


# --- a stand-in for the processing simulator ------------------------------------------------

class FakeSimulator:
    """Answers /sim/* like the real simulator's test cards, through httpx.MockTransport.

    `mode` changes how replies come back: "normal", "bad_signature", "unsigned", "http_500".
    """

    APPROVE = frozenset({"4242424242424242", "5555555555554444"})
    DECLINE: ClassVar = {"4000000000009995": "insufficient_funds",
                         "4000000000000002": "card_declined"}
    HANG = frozenset({"4000000000000119", "4000000000000127", "4000000000000135"})

    def __init__(self, secret):
        self.secret = secret
        self.mode = "normal"
        self.requests = []  # (method, path, json body or None)
        self.records = {}

    def record(self, body, status, reason=None):
        number = body["card"]["number"]
        return {
            "operation_id": body["operation_id"], "object": "operation", "type": "authorise",
            "status": status, "decline_reason": reason, "merchant_id": body["merchant_id"],
            "payment_id": body["payment_id"], "authorisation_id": None, "refund_id": None,
            "amount": body["amount"], "currency": "SGD",
            "card": {"brand": "visa" if number.startswith("4") else "mastercard",
                     "last4": number[-4:]},
            "simulator_reference": "sim_" + "S" * 24,
            "authorisation": ({"state": "open", "authorised_amount": body["amount"],
                               "captured_amount": 0, "refunded_amount": 0}
                              if status == "approved" else None),
            "recorded_at": "2026-11-13T05:00:00Z",
        }

    def reply(self, data, status=200):
        import httpx

        from apps.events import signing

        raw = json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
        if self.mode == "http_500":
            return httpx.Response(500, content=b"{}", headers=headers)
        if self.mode != "unsigned":
            secret = "wrong-secret" if self.mode == "bad_signature" else self.secret
            headers["Simulator-Signature"] = signing.sign(raw, secret)
        return httpx.Response(status, content=raw, headers=headers)

    def __call__(self, request):
        import httpx

        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        assert request.headers["Authorization"].startswith("Bearer simk_")
        if request.url.path == "/sim/authorise":
            number = body["card"]["number"]
            if number in self.HANG:
                raise httpx.ReadTimeout("no reply", request=request)
            if number in self.APPROVE:
                rec = self.record(body, "approved")
            else:
                rec = self.record(body, "declined", self.DECLINE.get(number, "card_declined"))
            self.records[body["operation_id"]] = rec
            return self.reply(rec)
        raise AssertionError(f"unexpected call {request.url.path}")


@pytest.fixture
def fake_sim(settings, monkeypatch):
    import httpx

    from apps.payments import processor

    sim = FakeSimulator(settings.SIMULATOR_SIGNING_SECRET)
    monkeypatch.setattr(processor, "TRANSPORT", httpx.MockTransport(sim))
    return sim
