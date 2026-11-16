"""Capture and cancel (contract section 3, UC-24) and the 7-day auto-cancel (FR-TXN-05)."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.events import signing
from apps.events.models import OutboxEvent
from apps.payments import jobs
from apps.payments.models import Operation, Payment

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


@pytest.fixture
def authorised(shop, fake_sim):
    """A payment paid through the hosted checkout and authorised by the fake simulator."""
    from conftest import valid_body

    payment_id = shop.create_payment(valid_body()).json()["id"]
    payment = Payment.objects.get(public_id=payment_id)
    browser = APIClient()
    base = f"/checkout/{payment.checkout_session_id}"
    card = {"number": "4242424242424242", "expiry_month": 12, "expiry_year": 2030,
            "cvc": "123", "privacy_consent": True}
    assert browser.post(f"{base}/card", card, format="json").status_code == 200
    assert browser.post(f"{base}/submit", {}, format="json").status_code == 200
    payment.refresh_from_db()
    assert payment.status == "authorised"
    return payment


def post(shop, payment, action, body=None, key=None):
    return shop.post(f"/v1/payments/{payment.public_id}/{action}", body or {}, format="json",
                     headers={"Idempotency-Key": key or str(uuid.uuid4())})


def test_full_capture(shop, authorised, payment_schema, event_schema):
    r = post(shop, authorised, "capture")
    assert r.status_code == 200, r.content
    data = r.json()
    payment_schema.validate(data)
    assert (data["status"], data["captured_amount"]) == ("captured", 4590)
    assert data["refundable_amount"] == 4590 and data["captured_at"]
    assert signing.verify(r.content, r["SecurePay-Signature"], shop.secret)
    event = OutboxEvent.objects.get(payment=authorised, type="payment.captured")
    assert event.sequence == data["sequence"]
    assert event.payload["data"]["object"]["status"] == "captured"
    event_schema(event.payload)
    op = Operation.objects.get(type="capture")
    assert op.status == "succeeded" and op.evidence_signature
    assert AuditEvent.objects.filter(action="payment.captured",
                                     target_id=authorised.public_id).exists()


def test_partial_capture_once(shop, authorised):
    r = post(shop, authorised, "capture", {"amount": 4000})
    assert r.json()["captured_amount"] == 4000
    again = post(shop, authorised, "capture", {"amount": 100})
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "payment_already_captured"


def test_capture_more_than_authorised_is_422(shop, authorised, fake_sim):
    r = post(shop, authorised, "capture", {"amount": 4591})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "capture_exceeds_authorised"
    assert not Operation.objects.filter(type="capture").exists()
    assert all(path == "/sim/authorise" for _, path, _ in fake_sim.requests)


@pytest.mark.parametrize("body", [{"amount": 0}, {"amount": "10"}, {"amount": True},
                                  {"amount_to_capture": 1}])
def test_capture_body_is_checked(shop, authorised, body):
    r = post(shop, authorised, "capture", body)
    assert r.status_code == 400


def test_cancel(shop, authorised, payment_schema, event_schema):
    r = post(shop, authorised, "cancel")
    assert r.status_code == 200, r.content
    payment_schema.validate(r.json())
    assert r.json()["status"] == "cancelled"
    assert r.json()["outcome"]["reason"] == "merchant_cancelled"
    event_schema(OutboxEvent.objects.get(payment=authorised, type="payment.cancelled").payload)
    assert post(shop, authorised, "capture").json()["error"]["code"] == \
        "payment_already_cancelled"
    assert post(shop, authorised, "cancel", {"reason": "x"}).status_code == 409


def test_captured_payment_cannot_be_cancelled(shop, authorised):
    post(shop, authorised, "capture")
    r = post(shop, authorised, "cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "payment_already_captured"


def test_not_authorised_yet(shop, fake_sim):
    payment_id = shop.create_payment().json()["id"]
    r = shop.post(f"/v1/payments/{payment_id}/capture", {}, format="json",
                  headers={"Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code == 409 and r.json()["error"]["code"] == "payment_not_authorised"


def test_other_merchants_payment_is_404(other_shop, authorised):
    r = post(other_shop, authorised, "capture")
    assert r.status_code == 404


def test_idempotent_replay_does_not_capture_twice(shop, authorised, fake_sim):
    key = str(uuid.uuid4())
    first = post(shop, authorised, "capture", key=key)
    second = post(shop, authorised, "capture", key=key)
    assert second.status_code == 200 and second["Idempotent-Replayed"] == "true"
    assert second.content == first.content
    assert sum(1 for _, path, _ in fake_sim.requests if path == "/sim/capture") == 1


def test_retry_after_lost_reply_finds_the_same_operation(shop, authorised, fake_sim):
    """A crash after the simulator call but before the stored reply: the key is freed and
    the retry must not send a second capture."""
    key = str(uuid.uuid4())
    post(shop, authorised, "capture", key=key)
    from apps.payments.models import IdempotencyRecord

    IdempotencyRecord.objects.filter(key=key).delete()  # as if the reply was never stored
    r = post(shop, authorised, "capture", key=key)
    assert r.status_code == 200 and r.json()["status"] == "captured"
    assert Operation.objects.filter(type="capture").count() == 1
    assert sum(1 for _, path, _ in fake_sim.requests if path == "/sim/capture") == 1


def test_no_answer_is_202_with_pending_operation(shop, authorised, fake_sim, payment_schema):
    fake_sim.settle_mode = "hang"
    r = post(shop, authorised, "capture")
    assert r.status_code == 202, r.content
    payment_schema.validate(r.json())
    assert r.json()["status"] == "authorised"
    assert r.json()["pending_operation"]["type"] == "capture"
    assert r.json()["pending_operation"]["status"] == "unresolved"
    assert not OutboxEvent.objects.filter(type="payment.captured").exists()
    again = post(shop, authorised, "cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "operation_in_progress"


def test_processor_disagreement_is_409_and_payment_unchanged(shop, authorised, fake_sim):
    fake_sim.settle_mode = "decline"
    r = post(shop, authorised, "capture")
    assert r.status_code == 409 and r.json()["error"]["code"] == "processor_rejected"
    authorised.refresh_from_db()
    assert authorised.status == "authorised"
    assert Operation.objects.get(type="capture").status == "failed"


def test_capture_after_seven_days_is_refused(shop, authorised):
    Payment.objects.filter(pk=authorised.pk).update(
        authorised_at=timezone.now() - timedelta(days=7, seconds=1))
    r = post(shop, authorised, "capture")
    assert r.status_code == 409 and r.json()["error"]["code"] == "authorisation_expired"


# --- the worker's 7-day auto-cancel -----------------------------------------------------------

def test_auto_cancel_after_seven_days(shop, authorised, fake_sim):
    fresh = Payment.objects.get(pk=authorised.pk)
    Payment.objects.filter(pk=authorised.pk).update(
        authorised_at=timezone.now() - timedelta(days=7, minutes=1))
    assert jobs.expire_authorisations() == 1
    fresh.refresh_from_db()
    assert fresh.status == "cancelled"
    assert fresh.outcome_reason == "authorisation_expired"
    assert OutboxEvent.objects.filter(payment=fresh, type="payment.cancelled").exists()
    assert AuditEvent.objects.filter(action="payment.cancel_requested",
                                     actor_id="expire_authorisations").exists()
    r = post(shop, fresh, "capture")
    assert r.json()["error"]["code"] == "authorisation_expired"
    assert jobs.expire_authorisations() == 0


def test_auto_cancel_leaves_recent_and_pending_ones(shop, authorised, fake_sim):
    assert jobs.expire_authorisations() == 0
    fake_sim.settle_mode = "hang"
    post(shop, authorised, "capture")  # unresolved capture
    Payment.objects.filter(pk=authorised.pk).update(
        authorised_at=timezone.now() - timedelta(days=8))
    assert jobs.expire_authorisations() == 0  # waits for the capture to settle


def test_checkout_sessions_expire(shop):
    payment_id = shop.create_payment().json()["id"]
    Payment.objects.filter(public_id=payment_id).update(
        checkout_expires_at=timezone.now() - timedelta(seconds=1))
    assert jobs.expire_checkout_sessions() == 1
    payment = Payment.objects.get(public_id=payment_id)
    assert (payment.status, payment.outcome_reason) == ("expired", "checkout_expired")
    assert OutboxEvent.objects.filter(payment=payment, type="payment.expired").exists()
