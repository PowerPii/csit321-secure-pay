"""User-facing reliability measures (apps.status.measures, docs/RELIABILITY-MEASURES.md)."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.payments.models import Operation, Payment
from apps.status import measures
from conftest import valid_body

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


def made(shop, *, minutes_ago, status, reason="", decision="allow", took_ms=None):
    """A payment submitted `minutes_ago`, in its final state (written directly)."""
    payment = Payment.objects.get(public_id=shop.create_payment(valid_body()).json()["id"])
    submitted = timezone.now() - timedelta(minutes=minutes_ago)
    Payment.objects.filter(pk=payment.pk).update(
        status=status, outcome_reason=reason, screening_decision=decision,
        submitted_at=submitted,
        authorised_at=None if took_ms is None else submitted + timedelta(milliseconds=took_ms))
    return payment


def test_percentile_is_nearest_rank():
    assert measures.percentile([], 95) is None
    assert measures.percentile([5], 95) == 5
    values = list(range(1, 101))
    assert measures.percentile(values, 50) == 50
    assert measures.percentile(values, 95) == 95
    assert measures.percentile([1, 2, 3], 95) == 3


def test_measures_with_their_populations(shop):
    for ms in (100, 200, 300, 400):
        made(shop, minutes_ago=60, status="captured", took_ms=ms)
    made(shop, minutes_ago=60, status="authorised", decision="verify", took_ms=90_000)  # code typed
    made(shop, minutes_ago=60, status="declined", reason="card_declined")
    made(shop, minutes_ago=60, status="blocked", reason="fraud_rule", decision="block")
    made(shop, minutes_ago=60, status="blocked", reason="verification_expired", decision="verify")
    made(shop, minutes_ago=60, status="blocked", reason="screening_unavailable",
         decision="not_screened")
    made(shop, minutes_ago=60, status="unresolved")
    made(shop, minutes_ago=60, status="verification_required", decision="verify")
    made(shop, minutes_ago=2, status="processing")  # too recent to count
    made(shop, minutes_ago=60 * 30, status="unresolved")  # before the 24-hour window
    shop.create_payment(valid_body())  # never submitted: not in any population

    m = measures.build_measures()

    # Verified payments are not timed: the code's typing time is the customer's.
    assert m["checkout_time"]["count"] == 4
    assert m["checkout_time"]["p50_ms"] == 200 and m["checkout_time"]["p95_ms"] == 400
    a = m["definite_answers"]
    # 11 submitted in the window and settled; 1 waits for the customer.
    assert a["eligible"] == 10
    # 5 approved + 1 declined + 2 blocked on purpose; screening-unavailable and unresolved are not answers.
    assert a["answered"] == 8 and a["percent"] == 80.0
    assert a["breakdown"]["expected_block"] == 2
    assert a["excluded"] == {"waiting_on_customer": 1, "too_recent": 1}
    assert m["screening_unavailable"]["count"] == 1
    assert m["window"]["hours"] == 24 and m["environment"] == "local stack"


def test_oldest_outstanding_operation(shop):
    payment = made(shop, minutes_ago=30, status="unresolved")
    op = Operation.objects.create(payment=payment, type="authorise", status="unresolved",
                                  amount=payment.amount)
    Operation.objects.filter(pk=op.pk).update(created_at=timezone.now() - timedelta(minutes=12))
    o = measures.build_measures()["oldest_outstanding"]
    assert o["operations_open"] == 1
    assert 12 * 60 <= o["operation_age_seconds"] < 13 * 60


def test_no_traffic_gives_no_percentages(db):
    m = measures.build_measures()
    assert m["definite_answers"]["percent"] is None
    assert m["checkout_time"]["p95_ms"] is None
    assert m["oldest_outstanding"]["operation_age_seconds"] is None


def test_status_json_carries_the_measures(client):
    data = client.get("/status.json").json()
    assert set(data["measures"]) >= {"checkout_time", "definite_answers", "screening_unavailable",
                                     "oldest_outstanding", "window", "environment", "population"}


def test_reliability_report_command(shop, capsys):
    made(shop, minutes_ago=60, status="captured", took_ms=150)
    call_command("reliability_report")
    out = capsys.readouterr().out
    assert "1 of 1 = 100.0%" in out and "p95 150 ms over 1 payments" in out
