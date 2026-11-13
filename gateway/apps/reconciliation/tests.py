"""Simulator notifications to the gateway (SIMULATOR-CONTRACT.md section 9)."""
import json
import time

import pytest
from rest_framework.test import APIClient

from apps.events import signing
from apps.events.models import OutboxEvent
from apps.payments.models import Operation
from apps.payments.test_reconciliation import LOST_RESPONSE, pay

pytestmark = pytest.mark.django_db(databases=["default", "vault"])
URL = "/internal/simulator/notifications"


def notification(record, delivery=1, nid="ntf_" + "N" * 24):
    return json.dumps({"id": nid, "type": "operation.recorded",
                       "created_at": "2026-11-13T04:31:13Z", "delivery": delivery,
                       "data": record}, separators=(",", ":")).encode()


def send(body, secret, timestamp=None):
    header = signing.sign(body, secret, timestamp)
    return APIClient().post(URL, body, content_type="application/json",
                            HTTP_SIMULATOR_SIGNATURE=header)


def approved_record(operation, payment):
    return {"operation_id": operation.public_id, "object": "operation", "type": "authorise",
            "status": "approved", "decline_reason": None,
            "merchant_id": payment.merchant.public_id, "payment_id": payment.public_id,
            "authorisation_id": None, "refund_id": None, "amount": payment.amount,
            "currency": "SGD", "card": {"brand": "visa", "last4": "0119"},
            "simulator_reference": "sim_" + "S" * 24,
            "authorisation": {"state": "open", "authorised_amount": payment.amount,
                              "captured_amount": 0, "refunded_amount": 0},
            "recorded_at": "2026-11-13T04:31:12Z"}


def test_notification_settles_an_unresolved_payment_once(shop, fake_sim, settings):
    payment = pay(shop, LOST_RESPONSE)
    assert payment.status == "unresolved"
    operation = Operation.objects.get(payment=payment)
    body = notification(approved_record(operation, payment))
    first = send(body, settings.SIMULATOR_SIGNING_SECRET)
    assert first.status_code == 200 and first.json() == {"received": True, "applied": True}
    payment.refresh_from_db()
    operation.refresh_from_db()
    assert payment.status == "authorised" and operation.status == "succeeded"
    assert operation.evidence_body == body.decode()
    events = OutboxEvent.objects.filter(payment=payment, type="payment.authorised").count()
    # A second copy changes nothing and still gets 200.
    again = send(notification(approved_record(operation, payment), delivery=2),
                 settings.SIMULATOR_SIGNING_SECRET)
    assert again.status_code == 200 and again.json()["applied"] is False
    assert OutboxEvent.objects.filter(payment=payment, type="payment.authorised").count() == \
        events


def test_bad_or_old_signature_is_refused(shop, fake_sim, settings):
    payment = pay(shop, LOST_RESPONSE)
    operation = Operation.objects.get(payment=payment)
    body = notification(approved_record(operation, payment))
    assert send(body, "simsig_wrong").status_code == 400
    old = send(body, settings.SIMULATOR_SIGNING_SECRET, int(time.time()) - 301)
    assert old.status_code == 400 and old.json()["error"]["code"] == "signature_invalid"
    unsigned = APIClient().post(URL, body, content_type="application/json")
    assert unsigned.status_code == 400
    payment.refresh_from_db()
    assert payment.status == "unresolved"


def test_record_for_another_payment_is_ignored(shop, fake_sim, settings):
    payment = pay(shop, LOST_RESPONSE)
    operation = Operation.objects.get(payment=payment)
    record = approved_record(operation, payment) | {"payment_id": "pay_" + "X" * 24}
    response = send(notification(record), settings.SIMULATOR_SIGNING_SECRET)
    assert response.status_code == 200 and response.json()["applied"] is False
    payment.refresh_from_db()
    assert payment.status == "unresolved"


def test_unknown_operation_and_no_record_are_ignored(shop, fake_sim, settings):
    payment = pay(shop, LOST_RESPONSE)
    operation = Operation.objects.get(payment=payment)
    unknown = approved_record(operation, payment) | {"operation_id": "op_" + "Z" * 24}
    assert send(notification(unknown), settings.SIMULATOR_SIGNING_SECRET).json()[
        "applied"] is False
    no_record = approved_record(operation, payment) | {"status": "no_record"}
    assert send(notification(no_record), settings.SIMULATOR_SIGNING_SECRET).json()[
        "applied"] is False
    payment.refresh_from_db()
    assert payment.status == "unresolved"


def test_malformed_body_is_refused(settings, db):
    body = b'{"id": "ntf_x"}'
    assert send(body, settings.SIMULATOR_SIGNING_SECRET).status_code == 400
