"""Refunds with reservations (UC-24, FR-TXN-01 to FR-TXN-03, demo story S6)."""
import threading
import uuid

import pytest
from django.db import connection
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.events import signing
from apps.events.models import OutboxEvent
from apps.payments import reconciliation
from apps.payments.models import Operation, Payment
from apps.refunds.models import Refund

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


@pytest.fixture
def refund_schema():
    import json

    from jsonschema import Draft202012Validator

    from conftest import CONTRACTS

    return Draft202012Validator(json.loads((CONTRACTS / "schemas" / "refund.schema.json")
                                           .read_text()))


def captured_payment(shop, amount=None):
    from conftest import valid_body

    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": "4242424242424242", "expiry_month": 12, "expiry_year": 2030,
            "cvc": "123"}
    browser.post(f"{base}/card", card, format="json")
    browser.post(f"{base}/submit", {}, format="json")
    body = {"amount": amount} if amount else {}
    r = shop.post(f"/v1/payments/{payment.public_id}/capture", body, format="json",
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 200, r.content
    payment.refresh_from_db()
    return payment


@pytest.fixture
def captured(shop, fake_sim):
    return captured_payment(shop)


def refund(client, payment, amount, key=None, **extra):
    return client.post(f"/v1/payments/{payment.public_id}/refunds", {"amount": amount, **extra},
                       format="json", headers={"Idempotency-Key": key or str(uuid.uuid4())})


def test_partial_refund_completes(shop, captured, fake_sim, refund_schema, payment_schema,
                                  event_schema):
    r = refund(shop, captured, 1500, reason="One item returned")
    assert r.status_code == 201, r.content
    data = r.json()
    refund_schema.validate(data)
    assert (data["status"], data["amount"], data["reason"]) == ("completed", 1500,
                                                                "One item returned")
    assert data["payment_reference"] == captured.reference and data["completed_at"]
    assert data["reference"].startswith("RF-")
    assert signing.verify(r.content, r["SecurePay-Signature"], shop.secret)
    sent = [b for _, path, b in fake_sim.requests if path == "/sim/refund"]
    assert sent == [{"operation_id": Operation.objects.get(type="refund").public_id,
                     "authorisation_id": Operation.objects.get(type="authorise").public_id,
                     "refund_id": data["id"], "amount": 1500}]

    p = shop.get(f"/v1/payments/{captured.public_id}").json()
    payment_schema.validate(p)
    assert p["status"] == "captured"
    assert (p["refunded_amount"], p["refund_reserved_amount"], p["refundable_amount"]) == (
        1500, 0, 3090)
    event = OutboxEvent.objects.get(payment=captured, type="refund.completed")
    event_schema(event.payload)
    assert event.payload["data"]["object"]["id"] == data["id"]
    assert event.sequence == p["sequence"]
    assert AuditEvent.objects.filter(action="refund.completed", target_id=data["id"]).exists()


def test_list_and_get(shop, other_shop, captured, refund_schema):
    first = refund(shop, captured, 1000).json()
    refund(shop, captured, 500)
    r = shop.get(f"/v1/payments/{captured.public_id}/refunds")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list" and body["refundable_amount"] == 3090
    assert [x["amount"] for x in body["data"]] == [1000, 500]
    one = shop.get(f"/v1/refunds/{first['id']}")
    refund_schema.validate(one.json())
    assert one.json() == first | {"updated_at": one.json()["updated_at"]}
    assert other_shop.get(f"/v1/refunds/{first['id']}").status_code == 404
    assert other_shop.get(f"/v1/payments/{captured.public_id}/refunds").status_code == 404


def test_refund_over_the_refundable_amount_is_422_and_creates_nothing(shop, captured):
    refund(shop, captured, 4000)
    r = refund(shop, captured, 591)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "refund_exceeds_refundable"
    assert "S$5.90" in r.json()["error"]["message"]
    assert Refund.objects.count() == 1
    assert AuditEvent.objects.filter(action="refund.rejected").count() == 1
    assert refund(shop, captured, 590).json()["status"] == "completed"
    assert refund(shop, captured, 1).status_code == 422


def test_refund_after_partial_capture_uses_the_captured_amount(shop, fake_sim):
    payment = captured_payment(shop, amount=4000)
    assert refund(shop, payment, 4001).status_code == 422
    assert refund(shop, payment, 4000).json()["status"] == "completed"


def test_refund_needs_a_captured_payment(shop, fake_sim):
    from conftest import valid_body

    payment_id = shop.create_payment(valid_body()).json()["id"]
    r = shop.post(f"/v1/payments/{payment_id}/refunds", {"amount": 100}, format="json",
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "payment_not_captured"


@pytest.mark.parametrize("body", [{}, {"amount": 0}, {"amount": "10"}, {"amount": True},
                                  {"amount": 100, "reason": "x" * 201},
                                  {"amount": 100, "note": "x"}])
def test_body_is_checked(shop, captured, body):
    r = shop.post(f"/v1/payments/{captured.public_id}/refunds", body, format="json",
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 400


def test_same_key_replays_and_never_refunds_twice(shop, captured, fake_sim):
    key = str(uuid.uuid4())
    first = refund(shop, captured, 1000, key=key)
    again = refund(shop, captured, 1000, key=key)
    assert again.status_code == 201 and again["Idempotent-Replayed"] == "true"
    assert again.json()["id"] == first.json()["id"]
    assert sum(1 for _, path, _ in fake_sim.requests if path == "/sim/refund") == 1


def test_no_answer_keeps_the_amount_reserved_until_reconciliation(shop, captured, fake_sim,
                                                                  refund_schema,
                                                                  event_schema):
    fake_sim.refund_mode = "hang"  # recorded, reply lost
    r = refund(shop, captured, 1500)
    assert r.status_code == 201
    refund_schema.validate(r.json())
    assert r.json()["status"] == "unresolved"
    p = shop.get(f"/v1/payments/{captured.public_id}").json()
    assert (p["refund_reserved_amount"], p["refundable_amount"]) == (1500, 3090)
    event_schema(OutboxEvent.objects.get(type="refund.unresolved").payload)
    # Nothing new while it is unresolved (SIMULATOR-CONTRACT.md section 3 rule 5).
    blocked = refund(shop, captured, 100)
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == \
        "operation_in_progress"

    Operation.objects.filter(type="refund").update(next_check_at=None)
    reconciliation.reconcile_due()
    p = shop.get(f"/v1/payments/{captured.public_id}").json()
    assert (p["refunded_amount"], p["refund_reserved_amount"]) == (1500, 0)
    assert Refund.objects.get().status == "completed"
    assert OutboxEvent.objects.filter(type="refund.completed").exists()


def test_refund_the_simulator_never_got_fails_and_releases_the_reservation(shop, captured,
                                                                          fake_sim):
    fake_sim.refund_mode = "lost"
    assert refund(shop, captured, 4590).json()["status"] == "unresolved"
    Operation.objects.filter(type="refund").update(next_check_at=None)
    reconciliation.reconcile_due()
    rfd = Refund.objects.get()
    assert (rfd.status, rfd.failure_reason) == ("failed", "not_processed")
    p = shop.get(f"/v1/payments/{captured.public_id}").json()
    assert (p["refunded_amount"], p["refund_reserved_amount"], p["refundable_amount"]) == (
        0, 0, 4590)
    assert OutboxEvent.objects.filter(type="refund.failed").exists()


def test_processor_decline_fails_the_refund(shop, captured, fake_sim):
    fake_sim.refund_mode = "decline"
    data = refund(shop, captured, 100).json()
    assert (data["status"], data["failure_reason"]) == ("failed", "declined_by_processor")
    assert shop.get(f"/v1/payments/{captured.public_id}").json()["refundable_amount"] == 4590


@pytest.mark.django_db(transaction=True, databases=["default", "vault"])
def test_two_refunds_at_once_cannot_exceed_the_payment(shop, fake_sim):
    """Demo story S6: 3000 + 3000 against 4590. Exactly one wins, under the row lock."""
    payment = captured_payment(shop)
    barrier = threading.Barrier(2)
    results = []

    def run():
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {shop.key}")
        barrier.wait()
        try:
            results.append(refund(client, payment, 3000).status_code)
        finally:
            connection.close()

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [201, 422]
    assert Refund.objects.filter(payment=payment).count() == 1
    p = shop.get(f"/v1/payments/{payment.public_id}").json()
    assert (p["refunded_amount"], p["refundable_amount"]) == (3000, 1590)
