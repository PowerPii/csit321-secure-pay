"""Shared steps for the acceptance tests of the non-functional requirements (URS 4.4)."""
import uuid

from rest_framework.test import APIClient

from apps.payments.models import Payment

APPROVE = "4242424242424242"
LOST_RESPONSE = "4000000000000119"


def card(number=APPROVE):
    return {"number": number, "expiry_month": 12, "expiry_year": 2030, "cvc": "123",
            "privacy_consent": True}


def new_payment(shop, **body) -> Payment:
    from conftest import valid_body

    r = shop.create_payment(valid_body(**body))
    assert r.status_code == 201, r.content
    return Payment.objects.get(public_id=r.json()["id"])


def submit(payment, number=APPROVE, browser=None):
    browser = browser or APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    r = browser.post(f"{base}/card", card(number), format="json")
    assert r.status_code == 200, r.content
    return browser.post(f"{base}/submit", {}, format="json")


def pay(shop, number=APPROVE, **body) -> Payment:
    payment = new_payment(shop, **body)
    submit(payment, number)
    payment.refresh_from_db()
    return payment


def capture(shop, payment):
    r = shop.post(f"/v1/payments/{payment.public_id}/capture", {}, format="json",
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.content
    payment.refresh_from_db()
    return payment


def refund(client, payment, amount, key=None):
    return client.post(f"/v1/payments/{payment.public_id}/refunds", {"amount": amount},
                       format="json", headers={"Idempotency-Key": key or str(uuid.uuid4())})


def json_post(client, path, body=None):
    return client.post(path, body or {}, content_type="application/json")
