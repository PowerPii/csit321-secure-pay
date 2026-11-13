"""Capture and cancel against an authorisation (SIMULATOR-CONTRACT.md section 4)."""
import pytest
from django.db.models import Sum

from apps.ledger.models import LedgerEntry
from apps.operations.models import Authorisation

AUTH = "op_" + "A" * 24
CAP = "op_" + "K" * 24
CAN = "op_" + "N" * 24
MER = "mer_" + "B" * 24
PAY = "pay_" + "C" * 24


@pytest.fixture
def authorised(gw):
    r = gw.post_json("/sim/authorise", {
        "operation_id": AUTH, "merchant_id": MER, "payment_id": PAY, "amount": 4590,
        "currency": "SGD",
        "card": {"number": "4242424242424242", "expiry_month": 12, "expiry_year": 2030,
                 "cvc": "123"}})
    assert r.status_code == 200 and r.json()["status"] == "approved"
    return r.json()


def balance(account):
    return LedgerEntry.objects.filter(account=account).aggregate(s=Sum("amount"))["s"] or 0


def test_partial_capture_charges_and_releases_the_rest(gw, authorised, operation_schema):
    r = gw.post_json("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH,
                                      "amount": 4000})
    data = r.json()
    assert r.status_code == 200
    operation_schema.validate(data)
    assert data["status"] == "approved" and data["type"] == "capture"
    assert data["payment_id"] == PAY and data["authorisation_id"] == AUTH
    assert data["authorisation"] == {"state": "captured", "authorised_amount": 4590,
                                     "captured_amount": 4000, "refunded_amount": 0}
    assert balance(LedgerEntry.Account.MERCHANT_SETTLEMENT) == 4000
    assert balance(LedgerEntry.Account.CARDHOLDER_HELD) == 0
    assert balance(LedgerEntry.Account.CARDHOLDER_AVAILABLE) == -4000
    assert sum(LedgerEntry.objects.filter(operation_id=CAP).values_list("amount", flat=True)) == 0


def test_capture_is_once_only(gw, authorised):
    gw.post_json("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH, "amount": 100})
    r = gw.post_json("/sim/capture", {"operation_id": "op_" + "L" * 24,
                                      "authorisation_id": AUTH, "amount": 100})
    assert r.json()["status"] == "declined"
    assert r.json()["decline_reason"] == "authorisation_not_open"


def test_capture_above_authorised_is_declined(gw, authorised, operation_schema):
    r = gw.post_json("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH,
                                      "amount": 4591})
    operation_schema.validate(r.json())
    assert (r.json()["status"], r.json()["decline_reason"]) == ("declined",
                                                                 "capture_exceeds_authorised")
    assert Authorisation.objects.get().state == "open"


def test_cancel_releases_the_hold_and_blocks_capture(gw, authorised, operation_schema):
    r = gw.post_json("/sim/cancel", {"operation_id": CAN, "authorisation_id": AUTH})
    operation_schema.validate(r.json())
    assert r.json()["status"] == "approved" and r.json()["amount"] == 4590
    assert r.json()["authorisation"]["state"] == "cancelled"
    assert balance(LedgerEntry.Account.CARDHOLDER_HELD) == 0
    assert balance(LedgerEntry.Account.CARDHOLDER_AVAILABLE) == 0
    r = gw.post_json("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH,
                                      "amount": 100})
    assert r.json()["decline_reason"] == "authorisation_not_open"


def test_repeat_replays_and_reuse_conflicts(gw, authorised):
    body = {"operation_id": CAP, "authorisation_id": AUTH, "amount": 4590}
    first = gw.post_json("/sim/capture", body)
    again = gw.post_json("/sim/capture", body)
    assert again.status_code == 200
    assert again.json()["simulator_reference"] == first.json()["simulator_reference"]
    assert LedgerEntry.objects.filter(operation_id=CAP).count() == 2
    r = gw.post_json("/sim/capture", {**body, "amount": 1})
    assert r.status_code == 409 and r.json()["error"]["code"] == "operation_id_conflict"


def test_retired_id_is_refused(gw, authorised):
    gw.get(f"/sim/operations/{CAN}", {"type": "cancel"})
    r = gw.post_json("/sim/cancel", {"operation_id": CAN, "authorisation_id": AUTH})
    assert r.status_code == 409 and r.json()["error"]["code"] == "operation_retired"
    assert Authorisation.objects.get().state == "open"


def test_unknown_authorisation_is_declined(gw, db):
    r = gw.post_json("/sim/cancel", {"operation_id": CAN, "authorisation_id": AUTH})
    assert (r.json()["status"], r.json()["decline_reason"]) == ("declined",
                                                                 "authorisation_not_found")


@pytest.mark.parametrize(("path", "body", "code"), [
    ("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH}, "missing_field"),
    ("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH, "amount": 0},
     "invalid_field"),
    ("/sim/cancel", {"operation_id": CAN, "authorisation_id": AUTH, "amount": 1},
     "invalid_field"),
    ("/sim/cancel", {"operation_id": AUTH, "authorisation_id": AUTH}, "invalid_field"),
])
def test_bad_requests(gw, db, path, body, code):
    r = gw.post_json(path, body)
    assert r.status_code == 400 and r.json()["error"]["code"] == code
