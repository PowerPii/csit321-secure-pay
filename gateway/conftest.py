"""Shared fixtures for gateway tests."""
import json
import uuid
from pathlib import Path

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
