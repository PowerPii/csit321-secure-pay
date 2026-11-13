"""Refunds against a captured authorisation (SIMULATOR-CONTRACT.md section 4)."""
import pytest
from django.db.models import Sum

from apps.ledger.models import LedgerEntry
from apps.operations.models import Authorisation

AUTH = "op_" + "A" * 24
CAP = "op_" + "K" * 24
R1 = "op_" + "R" * 24
R2 = "op_" + "S" * 24
RFD1 = "rfd_" + "D" * 24
RFD2 = "rfd_" + "E" * 24
MER = "mer_" + "B" * 24
PAY = "pay_" + "C" * 24


@pytest.fixture
def authorised(gw):
    r = gw.post_json("/sim/authorise", {
        "operation_id": AUTH, "merchant_id": MER, "payment_id": PAY, "amount": 4590,
        "currency": "SGD",
        "card": {"number": "4242424242424242", "expiry_month": 12, "expiry_year": 2030,
                 "cvc": "123"}})
    assert r.json()["status"] == "approved"


@pytest.fixture
def captured(gw, authorised):
    r = gw.post_json("/sim/capture", {"operation_id": CAP, "authorisation_id": AUTH,
                                      "amount": 4000})
    assert r.json()["status"] == "approved"


def refund(gw, op, rfd, amount):
    return gw.post_json("/sim/refund", {"operation_id": op, "authorisation_id": AUTH,
                                        "refund_id": rfd, "amount": amount})


def balance(account):
    return LedgerEntry.objects.filter(account=account).aggregate(s=Sum("amount"))["s"] or 0


def test_partial_refunds_up_to_the_captured_amount(gw, captured, operation_schema):
    r = refund(gw, R1, RFD1, 1500)
    data = r.json()
    assert r.status_code == 200
    operation_schema.validate(data)
    assert (data["type"], data["status"], data["refund_id"]) == ("refund", "approved", RFD1)
    assert data["authorisation"]["refunded_amount"] == 1500
    assert balance(LedgerEntry.Account.MERCHANT_SETTLEMENT) == 2500
    assert sum(LedgerEntry.objects.filter(operation_id=R1).values_list("amount", flat=True)) == 0

    r = refund(gw, R2, RFD2, 2501)
    assert (r.json()["status"], r.json()["decline_reason"]) == ("declined",
                                                                 "refund_exceeds_captured")
    assert Authorisation.objects.get().refunded_amount == 1500
    assert LedgerEntry.objects.filter(operation_id=R2).count() == 0
    assert refund(gw, R2, RFD2, 2500).status_code == 409  # same ID, other request


def test_refund_before_capture_is_declined(gw, authorised):
    r = refund(gw, R1, RFD1, 100)
    assert r.json()["decline_reason"] == "authorisation_not_captured"


def test_repeat_is_replayed_once(gw, captured):
    first = refund(gw, R1, RFD1, 1000)
    again = refund(gw, R1, RFD1, 1000)
    assert again.status_code == 200 and again["Simulator-Replayed"] == "true"
    assert again.json()["simulator_reference"] == first.json()["simulator_reference"]
    assert Authorisation.objects.get().refunded_amount == 1000


def test_status_query_finds_the_refund_or_retires_the_id(gw, captured):
    refund(gw, R1, RFD1, 1000)
    r = gw.get(f"/sim/operations/{R1}", {"type": "refund"})
    assert (r.json()["status"], r.json()["refund_id"]) == ("approved", RFD1)
    r = gw.get(f"/sim/operations/{R2}", {"type": "refund"})
    assert (r.json()["status"], r.json()["type"]) == ("no_record", "refund")
    late = refund(gw, R2, RFD2, 1000)
    assert late.status_code == 409 and late.json()["error"]["code"] == "operation_retired"
    assert Authorisation.objects.get().refunded_amount == 1000


def test_bad_refund_id(gw, captured):
    r = refund(gw, R1, "rfd_short", 1000)
    assert r.status_code == 400 and r.json()["error"]["param"] == "refund_id"
