"""Fraud insights charts page (extends FR-FRD-10, UC-52): role access, counts, scores, lines."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.internal.tests import pay
from apps.risk.models import ScreeningEvent

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


@pytest.fixture
def analyst(staff_client):
    return staff_client("fraud_analyst")


@pytest.fixture
def screened(shop, fake_sim):
    call_command("seed_risk_lists")
    allowed = pay(shop)
    blocked = pay(shop, customer_email="blocked@example.com")
    verify = pay(shop, customer_email="review@example.com")
    assert (allowed.status, blocked.status, verify.status) == (
        "authorised", "blocked", "verification_required")
    return allowed, blocked, verify


def test_only_analysts_and_administrators_see_insights(staff_client, shop):
    operator = staff_client("merchant_operator", merchant=shop.merchant)
    assert operator.get("/internal/insights/fraud").status_code == 403
    assert staff_client("administrator").get("/internal/insights/fraud").status_code == 200


def test_outcomes_rules_and_stage_are_counted(analyst, screened):
    data = analyst.get("/internal/insights/fraud?range=24h").json()
    assert data["interval"] == "hour" and len(data["outcomes"]) == 24
    assert data["totals"] == {"screened": 3, "allowed": 1, "verify": 1, "blocked": 1,
                              "not_screened": 0}
    last = data["outcomes"][-1]
    assert (last["allowed"], last["verify"], last["blocked"]) == (1, 1, 1)
    assert data["decided_by"] == {"rules": 2, "model": 0, "allowed": 1, "unavailable": 0}
    rules = {r["reason"]: r for r in data["top_rules"]}
    assert rules["blocklisted_email"] == {"reason": "blocklisted_email", "blocked": 1,
                                          "verify": 0, "total": 1}
    assert rules["review_list_email"]["verify"] == 1


def test_scores_points_histogram_and_thresholds(analyst, screened):
    _, blocked, _ = screened
    data = analyst.get("/internal/insights/fraud?range=7d").json()
    assert data["interval"] == "day" and len(data["outcomes"]) == 7
    scores = data["scores"]
    assert scores["scored"] == 3 and len(scores["points"]) == 3
    case = next(p for p in scores["points"] if p["outcome"] == "blocked")
    assert case["case_id"] == blocked.screening.public_id  # opens the D6b case
    assert next(p for p in scores["points"] if p["outcome"] == "allowed")["case_id"] is None
    assert sum(b["allowed"] + b["verify"] + b["blocked"] for b in scores["histogram"]) == 3
    assert len(scores["histogram"]) == 50
    lines = data["thresholds"]
    assert lines["stub_model"] is True and lines["policy_version"] == "policy-0.1"
    assert (lines["verify"], lines["block"]) == (0.5, 0.9)


def test_range_merchant_filter_and_audit(analyst, screened, make_merchant):
    old = ScreeningEvent.objects.order_by("id").first()
    old.occurred_at = timezone.now() - timedelta(days=10)
    old.save(update_fields=["occurred_at"])
    assert analyst.get("/internal/insights/fraud?range=7d").json()["totals"]["screened"] == 2
    assert analyst.get("/internal/insights/fraud?range=30d").json()["totals"]["screened"] == 3

    other = make_merchant(name="Other shop")
    data = analyst.get(f"/internal/insights/fraud?range=30d&merchant={other.merchant.public_id}")
    assert data.json()["totals"]["screened"] == 0
    assert analyst.get("/internal/insights/fraud?range=1y").status_code == 400
    assert analyst.get("/internal/insights/fraud?merchant=mer_nope").status_code == 400
    entry = AuditEvent.objects.filter(action="fraud_insights.generated").last()
    assert entry.actor_id == analyst.account.public_id and entry.details["range"] == "30d"
