"""Why screening decided: what analysts and merchant operators see (apps.risk.explain)."""
import pytest
from django.core.management import call_command

from apps.internal.tests import pay
from apps.risk.models import ScreeningEvent

pytestmark = pytest.mark.django_db(databases=["default", "vault"])


@pytest.fixture
def analyst(staff_client):
    return staff_client("fraud_analyst")


@pytest.fixture
def operator(staff_client, shop):
    return staff_client("merchant_operator", merchant=shop.merchant)


MODEL_FACTORS = [
    {"source": "model", "feature": "card_attempts_10m", "value": 4.0, "effect": 1.2,
     "direction": "raises", "text": "4 earlier tries with this card in the last 10 minutes",
     "area": "Unusual activity on this card"},
    {"source": "model", "feature": "amount_cents", "value": 60000.0, "effect": -0.3,
     "direction": "lowers", "text": "amount S$600.00", "area": "Unusually large amount"},
]


@pytest.fixture
def stepped_up(shop, fake_sim):
    payment = pay(shop, amount=60_000)  # over the high_amount rule (S$500): step-up
    assert payment.status == "verification_required"
    return payment


def test_each_decision_stores_its_explanation(stepped_up):
    why = ScreeningEvent.objects.get(payment=stepped_up).explanation
    assert why["version"] == "explain-1"
    assert why["factors"][0]["code"] == "high_amount"
    assert why["factors"][0]["text"] == "Rule high_amount: Amount > S$500.00 (was S$600.00)"


def test_analyst_sees_the_factors_on_the_case_and_payment(analyst, stepped_up):
    event = ScreeningEvent.objects.get(payment=stepped_up)
    case = analyst.get(f"/internal/reviews/{event.public_id}").json()
    assert case["headline"] == "amount > S$500.00"
    assert case["screening"]["explanation"]["factors"][0]["code"] == "high_amount"
    detail = analyst.get(f"/internal/payments/{stepped_up.public_id}").json()
    assert detail["screening"]["explanation"]["headline"] == "amount > S$500.00"


def test_merchant_operator_sees_broad_areas_only(operator, stepped_up):
    event = ScreeningEvent.objects.get(payment=stepped_up)
    event.explanation["factors"] += MODEL_FACTORS
    event.save(update_fields=["explanation"])
    detail = operator.get(f"/internal/payments/{stepped_up.public_id}").json()
    screening = detail["screening"]
    assert screening == {
        "id": event.public_id, "outcome": "verify", "occurred_at": screening["occurred_at"],
        "merchant_view": True,
        "explanation": {"areas": ["Unusually large amount", "Unusual activity on this card"]}}
    # No reason code, score, feature value, threshold or version anywhere in the reply.
    text = str(detail)
    for hidden in ("high_amount", "card_attempts", "score", "threshold", "rules-0",
                   "policy-", "stub-0", "fs-0", "effect", "500.00"):
        assert hidden not in text, hidden
    screening_row = next(r for r in detail["trail"] if r["kind"] == "screening")
    assert screening_row.get("detail") is None
    # The status history keeps the decision itself.
    step_up = next(e for e in detail["timeline"]
                   if e["action"] == "payment.verification_required")
    assert step_up["details"]["screening"] == "verify"


def test_merchant_operator_does_not_see_the_fraud_teams_review(operator, analyst, stepped_up):
    event = ScreeningEvent.objects.get(payment=stepped_up)
    analyst.post(f"/internal/reviews/{event.public_id}", {"action": "assign"}, format="json")
    seen = analyst.get(f"/internal/payments/{stepped_up.public_id}").json()
    assert any(e["action"] == "review.assigned" for e in seen["timeline"])
    detail = operator.get(f"/internal/payments/{stepped_up.public_id}").json()
    assert not any(e["action"].startswith("review.") for e in detail["timeline"])
    assert not any(r["title"].startswith("review.") for r in detail["trail"])


def test_analyst_and_admin_keep_the_full_decision_record(analyst, staff_client, stepped_up):
    admin = staff_client("administrator")
    for client in (analyst, admin):
        detail = client.get(f"/internal/payments/{stepped_up.public_id}").json()
        screening = detail["screening"]
        assert "merchant_view" not in screening
        assert screening["reasons"] == ["high_amount"]
        assert screening["score"] == 0.0 and screening["features"]
        assert screening["rules_version"] and screening["model_version"]
        row = next(r for r in detail["trail"] if r["kind"] == "screening")
        assert row["detail"] == "score 0.0000"


def test_insights_rank_the_features_that_raised_flagged_scores(analyst, stepped_up, shop):
    allowed = pay(shop)
    for payment in (stepped_up, allowed):
        event = ScreeningEvent.objects.get(payment=payment)
        event.explanation["factors"] = MODEL_FACTORS
        event.save(update_fields=["explanation"])
    data = analyst.get("/internal/insights/fraud?range=24h").json()
    # only flagged payments count, and only factors that raised the score
    assert data["top_factors"] == [{
        "feature": "card_attempts_10m", "verify": 1, "blocked": 0, "total": 1,
        "example": "4 earlier tries with this card in the last 10 minutes"}]


def test_older_records_can_be_explained_afterwards(stepped_up):
    ScreeningEvent.objects.filter(payment=stepped_up).update(explanation={})
    call_command("explain_decisions")
    why = ScreeningEvent.objects.get(payment=stepped_up).explanation
    assert why["method"] == "rules-only"  # the stub model has no contributions
    assert why["factors"][0]["code"] == "high_amount"
