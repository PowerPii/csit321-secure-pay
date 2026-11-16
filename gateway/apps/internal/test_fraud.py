"""Fraud alerts (FR-FRD-08, UC-50) and fraud reports (FR-FRD-10, UC-52)."""
import csv
import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.internal.tests import pay, post
from apps.internal.views.fraud import report_csv
from apps.internal.views.payments import local_zone
from apps.payments.models import Payment
from apps.risk.alerts import raise_fraud_alert
from apps.risk.models import FraudAlert, ScreeningEvent

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


@pytest.fixture
def analyst(staff_client):
    return staff_client("fraud_analyst")


@pytest.fixture
def admin(staff_client):
    return staff_client("administrator")


@pytest.fixture
def operator(staff_client, shop):
    return staff_client("merchant_operator", merchant=shop.merchant)


@pytest.fixture
def flagged(shop, fake_sim):
    call_command("seed_risk_lists")
    allowed = pay(shop)
    blocked = pay(shop, customer_email="blocked@example.com")
    verify = pay(shop, customer_email="review@example.com")
    assert (allowed.status, blocked.status, verify.status) == (
        "authorised", "blocked", "verification_required")
    return allowed, blocked, verify


# --- alerts ---------------------------------------------------------------------------------

def test_each_flagged_payment_raises_one_alert(analyst, flagged):
    _allowed, blocked, verify = flagged
    alerts = {a.screening.payment_id: a for a in FraudAlert.objects.select_related("screening")}
    assert set(alerts) == {blocked.pk, verify.pk}  # the allowed payment raised none

    data = analyst.get("/internal/alerts").json()
    assert data["count"] == 2 and data["unread"] == 2
    row = next(r for r in data["data"] if r["case"]["payment"]["id"] == blocked.public_id)
    assert row["read"] is False
    assert row["case"]["payment"]["reference"] == blocked.reference
    assert row["case"]["reasons"] == ["blocklisted_email"]
    assert "score" in row["case"]
    assert row["case"]["id"] == blocked.screening.public_id  # opens the D6b case


def test_same_event_never_raises_a_second_alert(flagged):
    _, blocked, verify = flagged
    event = ScreeningEvent.objects.get(payment=blocked)
    assert raise_fraud_alert(event) == event.alert
    assert raise_fraud_alert(ScreeningEvent.objects.get(payment=verify)) is not None
    assert FraudAlert.objects.count() == 2


def test_wrong_codes_on_a_verify_payment_add_no_alert(flagged):
    from rest_framework.test import APIClient

    _, _, verify = flagged
    browser = APIClient()
    for _ in range(3):
        browser.post(f"/checkout/{verify.checkout_session_id}/verify", {"code": "000000"},
                     format="json")
    verify.refresh_from_db()
    assert verify.status == "blocked"
    assert FraudAlert.objects.filter(screening__payment=verify).count() == 1
    assert FraudAlert.objects.count() == 2


def test_read_state_is_per_staff_member(analyst, admin, flagged):
    alert = analyst.get("/internal/alerts").json()["data"][0]
    r = post(analyst, f"/internal/alerts/{alert['id']}/read")
    assert r.status_code == 200 and r.json()["read"] is True
    assert analyst.get("/internal/alerts/unread").json()["unread"] == 1
    assert admin.get("/internal/alerts/unread").json()["unread"] == 2  # not hidden from others

    unread = analyst.get("/internal/alerts?show=unread").json()
    assert unread["count"] == 1 and unread["data"][0]["id"] != alert["id"]

    assert post(analyst, "/internal/alerts/read-all").json()["marked"] == 1
    assert analyst.get("/internal/alerts/unread").json() == {"unread": 0, "latest_at": None}
    assert post(analyst, f"/internal/alerts/{alert['id']}/read").status_code == 200  # idempotent
    assert post(analyst, "/internal/alerts/fal_missing/read").status_code == 404


def test_alerts_are_for_analysts_and_administrators_only(operator, client, flagged):
    for path in ("/internal/alerts", "/internal/alerts/unread", "/internal/reports/fraud",
                 "/internal/reports/fraud/export"):
        assert operator.get(path).status_code == 403
        assert client.get(path).status_code == 401
    assert post(operator, "/internal/alerts/read-all").status_code == 403


def test_alert_appears_on_the_dashboard_within_10_seconds(analyst, shop, fake_sim):
    """NFR-PER-03 at the API: the alert is there as soon as checkout answers."""
    call_command("seed_risk_lists")
    for _ in range(20):
        started = timezone.now()
        pay(shop, customer_email="blocked@example.com")
        latest = analyst.get("/internal/alerts?page_size=1").json()["data"][0]
        assert (timezone.now() - started).total_seconds() < 10
        assert latest["case"]["decision"] == "blocked"
    assert analyst.get("/internal/alerts/unread").json()["unread"] == 20


# --- reports --------------------------------------------------------------------------------

def test_report_counts_decisions_findings_and_trend(analyst, flagged):
    _, blocked, _ = flagged
    case = blocked.screening.public_id
    post(analyst, f"/internal/reviews/{case}", {"action": "save", "finding": "confirmed_fraud"})

    data = analyst.get("/internal/reports/fraud").json()
    t = data["totals"]
    assert (t["screened"], t["allowed"], t["flagged"], t["blocked"], t["verify"]) == (3, 1, 2, 1, 1)
    assert t["flag_rate"] == round(2 / 3, 4)
    assert t["blocked_amount"] == blocked.amount
    assert data["decisions"] == {"blocked": 1, "verify_failed": 0, "verify_passed": 0,
                                 "verify_pending": 1}
    assert data["findings"] == {"confirmed_fraud": 1, "false_positive": 0, "inconclusive": 0,
                                "unreviewed": 1}
    assert sum(level["count"] for level in data["risk_levels"]) == 2
    assert {r["reason"] for r in data["top_reasons"]} >= {"blocklisted_email"}
    assert data["period"]["interval"] == "day" and len(data["trend"]) == 30
    today = data["trend"][-1]
    assert today["start"] == data["period"]["to"]
    assert (today["screened"], today["flagged"], today["blocked"], today["confirmed_fraud"]) == (
        3, 2, 1, 1)
    assert sum(d["screened"] for d in data["trend"]) == 3

    entry = AuditEvent.objects.filter(action="fraud_report.generated").last()
    assert entry.actor_id and entry.details["from"] == data["period"]["from"]


def test_report_filters_by_merchant_and_period(analyst, flagged, other_shop):
    data = analyst.get(f"/internal/reports/fraud?merchant={other_shop.merchant.public_id}").json()
    assert data["totals"]["screened"] == 0 and data["merchant"]["name"] == "Other Shop"
    assert [m["name"] for m in data["merchants"]] == ["Demo Shop"]
    assert data["findings"]["unreviewed"] == 0

    # The report counts days in Singapore time, so take the date there (after 16:00 UTC the
    # UTC date is a day behind).
    old = (timezone.now() - timedelta(days=60)).astimezone(local_zone()).date()
    data = analyst.get(f"/internal/reports/fraud?from={old}&to={old + timedelta(days=6)}").json()
    assert data["totals"]["screened"] == 0  # no data: an empty report, not an error
    assert len(data["trend"]) == 7

    # Older events count on the day they happened, not today.
    ScreeningEvent.objects.update(occurred_at=timezone.now() - timedelta(days=60))
    data = analyst.get(f"/internal/reports/fraud?from={old - timedelta(days=1)}&to={old}").json()
    assert data["totals"]["screened"] == 3


def test_report_refuses_an_invalid_period(analyst):
    r = analyst.get("/internal/reports/fraud?from=2026-11-10&to=2026-11-01")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_period"
    r = analyst.get("/internal/reports/fraud?from=2024-01-01&to=2026-11-01")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_period"
    assert analyst.get("/internal/reports/fraud?from=13-11-2026").status_code == 400
    assert analyst.get("/internal/reports/fraud?interval=year").status_code == 400
    assert analyst.get("/internal/reports/fraud?merchant=mer_nope").status_code == 400


def test_long_periods_are_grouped_by_week(analyst):
    data = analyst.get("/internal/reports/fraud?from=2026-08-03&to=2026-11-15").json()
    assert data["period"]["interval"] == "week"
    assert data["trend"][0]["start"] == "2026-08-03"  # a Monday
    assert len(data["trend"]) == 15


def test_report_exports_as_csv(admin, flagged):
    r = admin.get("/internal/reports/fraud/export")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("text/csv")
    assert "attachment; filename=\"fraud-report-" in r["Content-Disposition"]
    rows = list(csv.reader(io.StringIO(r.content.decode())))
    assert rows[0] == ["SecurePay fraud report"]
    assert ["Flagged (block or verify)", "2"] in rows
    assert ["Blocked", "1"] in rows
    assert AuditEvent.objects.filter(action="fraud_report.exported").count() == 1
    # Nothing in the file can identify a card or a customer.
    text = r.content.decode()
    assert "blocked@example.com" not in text and "4242" not in text


def test_csv_cells_cannot_run_as_formulas():
    report = {
        "period": {"from": "2026-11-01", "to": "2026-11-02", "interval": "day",
                   "time_zone": "Asia/Singapore"},
        "merchant": {"id": "mer_x", "name": "=HYPERLINK(\"http://evil\")"},
        "generated_at": "2026-11-02T00:00:00Z",
        "totals": dict.fromkeys(("screened", "allowed", "flagged", "blocked", "verify",
                                 "not_screened", "flagged_amount", "blocked_amount"), 0)
        | {"flag_rate": 0.0},
        "decisions": dict.fromkeys(("blocked", "verify_failed", "verify_passed",
                                    "verify_pending"), 0),
        "risk_levels": [], "findings": dict.fromkeys(
            ("confirmed_fraud", "false_positive", "inconclusive", "unreviewed"), 0),
        "top_reasons": [{"reason": "@SUM(1)", "count": 1}], "trend": [],
    }
    rows = list(csv.reader(io.StringIO(report_csv(report))))
    assert ["Merchant", "'=HYPERLINK(\"http://evil\")"] in rows
    assert ["'@SUM(1)", "1"] in rows


def test_unscreened_attempts_raise_no_fraud_alert(shop, fake_sim, settings):
    settings.DEBUG = True
    settings.RISK_SIMULATE_OUTAGE = "error"
    payment = pay(shop)
    assert Payment.objects.get(pk=payment.pk).screening_decision == "not_screened"
    assert FraudAlert.objects.count() == 0
