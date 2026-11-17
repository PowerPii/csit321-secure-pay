"""Fixtures for the cross-service tests: they talk to the running Compose stack over HTTPS.

Needs `docker compose -f deploy/compose.yaml up` with the demo shop registered (README
quick start, step 4) and SIM_TEST_CONTROLS=1 (the Compose default). See README.md here.
"""
import os
import re
import ssl
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
SECRETS = ROOT / "deploy" / "secrets"
GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://gateway.localhost")
SIMULATOR_URL = os.environ.get("SIMULATOR_URL", "https://simulator.localhost")
MERCHANT_URL = os.environ.get("MERCHANT_URL", "https://shop.localhost")
MAILPIT_URL = os.environ.get("MAILPIT_URL", "https://mail.localhost")

# IT_APPROVE_CARD: a fresh demo card (simulator `new_demo_card`) for `demo.sh preflight`, whose
# one test payment must not be blocked by the fixed card's screening history.
APPROVE = os.environ.get("IT_APPROVE_CARD", "4242424242424242").replace(" ", "")
APPROVE_2 = "5555555555554444"
DECLINE = "4000000000000002"
LOST_RESPONSE = "4000000000000119"
SLOW = "4000000000000127"
BLOCKLISTED = "4000000000000101"


def _secret(name: str) -> str:
    return (SECRETS / name).read_text().strip()


@pytest.fixture(scope="session")
def ca_bundle(tmp_path_factory) -> str:
    """Caddy's local root certificate (public part), from CADDY_ROOT_CA or the container."""
    if os.environ.get("CADDY_ROOT_CA"):
        return os.environ["CADDY_ROOT_CA"]
    path = tmp_path_factory.mktemp("ca") / "root.crt"
    subprocess.run(["docker", "compose", "-f", str(ROOT / "deploy" / "compose.yaml"), "cp",
                    "caddy:/ca/root.crt", str(path)], check=True, capture_output=True)
    return str(path)


def _client(ca_bundle, base_url, **kwargs) -> httpx.Client:
    # trust_env=False: never send these local calls through an outbound proxy.
    return httpx.Client(base_url=base_url, verify=ssl.create_default_context(cafile=ca_bundle),
                        trust_env=False, timeout=30, **kwargs)


@pytest.fixture(scope="session")
def urls():
    return {"gateway": GATEWAY_URL, "simulator": SIMULATOR_URL, "merchant": MERCHANT_URL}


@pytest.fixture(scope="session")
def merchant_api(ca_bundle):
    """The demo shop's SecurePay API key (deploy/secrets/securepay_api_key)."""
    with _client(ca_bundle, GATEWAY_URL,
                 headers={"Authorization": f"Bearer {_secret('securepay_api_key')}"}) as c:
        yield c


@pytest.fixture(scope="session")
def browser_factory(ca_bundle):
    clients = []

    def make(base_url=GATEWAY_URL, **kwargs):
        client = _client(ca_bundle, base_url, **kwargs)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


@pytest.fixture(scope="session")
def controls(ca_bundle):
    """The simulator's test controls (/sim/faults), with the test runner's own key."""
    key = _secret("simulator_test_control_key")
    with _client(ca_bundle, SIMULATOR_URL, headers={"Authorization": f"Bearer {key}"}) as c:
        if c.get("/sim/faults").status_code == 404:
            pytest.skip("simulator test controls are off (SIM_TEST_CONTROLS=0)")
        yield c


@pytest.fixture(autouse=True)
def _clear_faults(request):
    """No fault rule outlives the test that added it."""
    yield
    if "controls" in request.fixturenames:
        request.getfixturevalue("controls").delete("/sim/faults")


class Mailpit:
    def __init__(self, client: httpx.Client):
        self.client = client

    def wait_for(self, to: str, subject_contains: str, after: float, timeout: float = 30):
        """The newest message to `to` whose subject contains the text, received after `after`."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            found = self.client.get("/api/v1/search", params={"query": f'to:"{to}"'}).json()
            for summary in found.get("messages", []):
                ts = datetime.fromisoformat(summary["Created"].replace("Z", "+00:00")).timestamp()
                if subject_contains in summary["Subject"] and ts >= after - 2:
                    return self.client.get(f"/api/v1/message/{summary['ID']}").json()
            time.sleep(0.5)
        raise AssertionError(f"no email to {to} with {subject_contains!r} within {timeout} s")


@pytest.fixture(scope="session")
def mailpit(ca_bundle):
    with _client(ca_bundle, MAILPIT_URL) as c:
        yield Mailpit(c)


def unique_email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:10]}@example.com"


def create_payment(merchant_api, amount=4590, email=None, key=None, **extra):
    body = {"amount": amount, "currency": "SGD", "order_reference": f"IT-{uuid.uuid4().hex[:8]}",
            "return_url": f"{MERCHANT_URL}/orders/1/return",
            "customer_email": email or unique_email("guest"), **extra}
    response = merchant_api.post("/v1/payments", json=body,
                                 headers={"Idempotency-Key": key or str(uuid.uuid4())})
    assert response.status_code == 201, response.text
    return response.json()


def session_id(payment: dict) -> str:
    return re.search(r"(cs_[0-9A-Za-z]{24})", payment["checkout_url"]).group(1)


def pay(browser, payment: dict, card: str, timeout: float = 30) -> dict:
    """What the checkout page does: vault the card, then submit. Returns the session view."""
    base = f"/checkout/{session_id(payment)}"
    card_body = {"number": card, "expiry_month": 12, "expiry_year": 2030, "cvc": "123", "privacy_consent": True}
    response = browser.post(f"{base}/card", json=card_body)
    assert response.status_code == 200, response.text
    response = browser.post(f"{base}/submit", json={}, timeout=timeout)
    assert response.status_code == 200, response.text
    return response.json()


def wait_for_status(merchant_api, payment_id: str, wanted: set[str], timeout: float):
    deadline = time.time() + timeout
    while True:
        payment = merchant_api.get(f"/v1/payments/{payment_id}").json()
        if payment["status"] in wanted or time.time() > deadline:
            return payment
        time.sleep(1)
