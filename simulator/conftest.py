"""Shared fixtures for simulator tests."""
import json
from pathlib import Path

import pytest
from django.test import Client
from jsonschema import Draft202012Validator

CONTRACTS = Path(__file__).resolve().parent.parent / "contracts"


@pytest.fixture(autouse=True)
def _no_hold(settings):
    settings.SIM_HOLD_SECONDS = 0  # the hanging test cards reply at once in tests


@pytest.fixture(scope="session")
def operation_schema():
    schema = json.loads((CONTRACTS / "schemas" / "simulator-operation.schema.json").read_text())
    return Draft202012Validator(schema)


class GatewayClient(Client):
    def __init__(self, key, **kwargs):
        super().__init__(**kwargs)
        self.key = key

    def _auth(self, extra):
        extra.setdefault("HTTP_AUTHORIZATION", f"Bearer {self.key}")
        return extra

    def post_json(self, path, body, **extra):
        return self.post(path, json.dumps(body), content_type="application/json",
                         **self._auth(extra))

    def get(self, path, *args, **extra):
        return super().get(path, *args, **self._auth(extra))


@pytest.fixture
def gw(settings, db):
    return GatewayClient(settings.SIMULATOR_API_KEY)

