"""Plain-language explanations of screening decisions (apps.risk.explain; FR-FRD-01 record).

The model part is checked three ways: against a brute-force Shapley calculation of the same
(path-dependent) value function on a small model, for additivity against the model's own raw
output, and, when the gateway model is installed, against reference values from the `shap`
package's TreeExplainer (shap 0.54.1, scikit-learn 1.7.2, computed 18 Nov 2026).
"""
import itertools
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from django.conf import settings
from sklearn.ensemble import HistGradientBoostingClassifier

from apps.risk import explain
from apps.risk.explain import TreeShapExplainer, merchant_summary
from apps.risk.pipeline import Attempt, Outcome, Pipeline, Rules
from apps.risk.scoring import StubModel, Thresholds

NAMES = ["a", "b", "c", "d"]


@pytest.fixture(scope="module")
def small_model():
    rng = np.random.default_rng(321)
    X = rng.normal(size=(600, 4))
    y = ((X[:, 0] + 0.8 * X[:, 1] * X[:, 2] - 0.5 * X[:, 3] + rng.normal(scale=0.5, size=600))
         > 0.8).astype(int)
    return HistGradientBoostingClassifier(max_iter=25, max_leaf_nodes=8, random_state=0).fit(X, y)


def brute_force_shap(model, row):
    """Shapley values of v(S) = E[f(x) | x_S] with the trees' own sample counts as the
    distribution of the unknown features, by enumerating every coalition."""
    def tree_value(nodes, i, known):
        node = nodes[i]
        if node["is_leaf"]:
            return node["value"]
        left, right = node["left"], node["right"]
        if node["feature_idx"] in known:
            nxt = left if row[node["feature_idx"]] <= node["num_threshold"] else right
            return tree_value(nodes, nxt, known)
        lc, rc = nodes[left]["count"], nodes[right]["count"]
        return (tree_value(nodes, left, known) * lc + tree_value(nodes, right, known) * rc) / (
            lc + rc)

    def v(known):
        return sum(tree_value(t[0].nodes, 0, known) for t in model._predictors)

    n = len(row)
    phi = [0.0] * n
    for i in range(n):
        others = [j for j in range(n) if j != i]
        for size in range(n):
            w = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            for subset in itertools.combinations(others, size):
                phi[i] += w * (v(set(subset) | {i}) - v(set(subset)))
    return phi


def test_contributions_are_exact_shapley_values(small_model):
    explainer = TreeShapExplainer(small_model, NAMES)
    rng = np.random.default_rng(7)
    for row in rng.normal(size=(5, 4)):
        _, phi = explainer.contributions(dict(zip(NAMES, row, strict=True)))
        assert [phi[n] for n in NAMES] == pytest.approx(brute_force_shap(small_model, row),
                                                        abs=1e-9)


def test_contributions_add_up_to_the_model_output(small_model):
    explainer = TreeShapExplainer(small_model, NAMES)
    rows = np.random.default_rng(8).normal(size=(50, 4))
    rows[0, 2] = np.nan  # a missing value follows the trees' own missing-value direction
    raw = small_model.decision_function(rows)
    for row, expected in zip(rows, raw, strict=True):
        base, phi = explainer.contributions(dict(zip(NAMES, row, strict=True)))
        assert base + sum(phi.values()) == pytest.approx(expected, abs=1e-9)


# Reference values from shap.TreeExplainer on hgb-fs02-2026-11-13 (log-odds).
SHAP_EXPECTED = -3.763423895299897
SHAP_REFERENCE = [
    ({
        "amount_cents": 250000.0,
        "card_attempts_10m": 4.0,
        "card_attempts_1h": 4.0,
        "card_attempts_24h": 4.0,
        "card_attempts_7d": 4.0,
        "card_attempts_30d": 4.0,
        "card_seconds_since_last": 40.0,
        "card_mean_amount_30d": 50000.0,
        "amount_to_card_mean_30d": 5.0,
    },
     {
        "amount_cents": -1.2625490466935778,
        "card_attempts_10m": -0.03336834948653135,
        "card_attempts_1h": -0.000609933798875961,
        "card_attempts_24h": 0.02687754703444628,
        "card_attempts_7d": -0.03741891892993373,
        "card_attempts_30d": -0.09870098526984585,
        "card_seconds_since_last": 0.026906325432947915,
        "card_mean_amount_30d": -0.1840802237714358,
        "amount_to_card_mean_30d": 0.13226175025009654,
    },
     0.0055185531302754465),
    ({
        "amount_cents": 4500.0,
        "card_attempts_10m": 0.0,
        "card_attempts_1h": 0.0,
        "card_attempts_24h": 0.0,
        "card_attempts_7d": 0.0,
        "card_attempts_30d": 0.0,
        "card_seconds_since_last": -1.0,
        "card_mean_amount_30d": 0.0,
        "amount_to_card_mean_30d": 0.0,
    },
     {
        "amount_cents": 0.2356705920784538,
        "card_attempts_10m": 0.0021318952951297813,
        "card_attempts_1h": -0.019527176642539126,
        "card_attempts_24h": -0.019747667388468004,
        "card_attempts_7d": 0.06270456012663575,
        "card_attempts_30d": 0.033376774646578906,
        "card_seconds_since_last": 1.1504039736858764,
        "card_mean_amount_30d": -0.05818329082101901,
        "amount_to_card_mean_30d": -0.06611471557426839,
    },
     0.07997336713960555),
]


def test_gateway_model_matches_the_shap_package():
    from apps.risk.scoring import load_artifact

    folder = Path(settings.RISK_MODEL_DIR) / "hgb-fs02-2026-11-13"
    if not (folder / "model.joblib").is_file():
        pytest.skip("hgb-fs02-2026-11-13 is not installed here")
    model = load_artifact(folder)
    for features, reference, proba in SHAP_REFERENCE:
        base, phi = model.explain(features)
        assert base == pytest.approx(SHAP_EXPECTED, abs=1e-9)
        assert phi == pytest.approx(reference, abs=1e-9)
        assert explain.sigmoid(base + sum(phi.values())) == pytest.approx(proba, abs=1e-9)
        assert model.score(features) == pytest.approx(proba, abs=1e-9)


# --- words ------------------------------------------------------------------------------------

FEATURES = {"amount_cents": 250_000.0, "card_attempts_10m": 4.0, "card_attempts_30d": 0.0,
            "card_seconds_since_last": 40.0, "amount_to_card_mean_30d": 5.0,
            "card_mean_amount_30d": 50_000.0}


def test_rule_list_and_model_reasons_in_plain_words():
    why = explain.explain(
        outcome="block", reasons=["blocklisted_card", "card_attempt_burst", "model_score_high"],
        features=FEATURES, amount_cents=250_000, score=0.4,
        contributions=(-3.0, {"card_attempts_10m": 1.2, "amount_to_card_mean_30d": 0.6,
                              "card_attempts_30d": 0.4, "amount_cents": -0.3,
                              "card_seconds_since_last": 0.001}),
        rules={"card_attempt_burst": ("card_attempts_10m", "gte", 5.0)})
    assert why["method"] == "tree-shap"
    assert why["base_score"] == pytest.approx(1 / (1 + math.exp(3.0)), abs=1e-4)
    texts = [f["text"] for f in why["factors"]]
    assert texts[0] == "This card is on the blocklist"
    assert texts[1] == "Rule card_attempt_burst: Earlier tries with this card in 10 minutes ≥ 5 (was 4)"
    model = [f for f in why["factors"] if f["source"] == "model"]
    assert [f["feature"] for f in model] == ["card_attempts_10m", "amount_to_card_mean_30d",
                                             "card_attempts_30d", "amount_cents"]  # tiny one left out
    assert [f["text"] for f in model] == [
        "4 earlier tries with this card in the last 10 minutes",
        "amount 5.0× this card's usual",
        "new card: not seen in the last 30 days",
        "amount S$2,500.00",
    ]
    assert model[-1]["direction"] == "lowers"
    assert why["headline"] == ("this card is on the blocklist + earlier tries with this card in "
                               "10 minutes ≥ 5 + 4 earlier tries with this card in the last 10 "
                               "minutes + amount 5.0× this card's usual")


def test_allowed_payment_says_why_nothing_fired():
    why = explain.explain(outcome="allow", reasons=[], features=FEATURES, amount_cents=4500,
                          score=0.01, contributions=None)
    assert why["method"] == "rules-only" and why["factors"] == []
    assert why["headline"].startswith("Allowed")


def test_amount_limit_and_review_list():
    why = explain.explain(outcome="block", reasons=["amount_over_limit", "review_list_email"],
                          features={}, amount_cents=2_000_000, score=0.0, contributions=None,
                          max_amount=1_000_000)
    assert [f["text"] for f in why["factors"]] == [
        "Amount S$20,000.00 is over the gateway's limit (S$10,000.00 limit)",
        "This email address is on the review list"]


def test_merchant_summary_names_areas_only():
    why = explain.explain(
        outcome="block", reasons=["card_attempt_burst", "high_amount", "model_score_high"],
        features=FEATURES, amount_cents=250_000, score=0.4,
        contributions=(-3.0, {"card_attempts_10m": 1.2, "amount_to_card_mean_30d": 0.6,
                              "amount_cents": -0.3}),
        rules={"card_attempt_burst": ("card_attempts_10m", "gte", 5.0),
               "high_amount": ("amount_cents", "gt", 50_000.0)})
    areas = merchant_summary(why)
    assert areas == ["Unusual activity on this card", "Unusually large amount",
                     "Amount unusual for this card"]
    joined = " ".join(areas)
    assert not any(ch.isdigit() for ch in joined)  # no thresholds or values
    assert "burst" not in joined and "rule" not in joined.lower()
    assert merchant_summary({}) == [] and merchant_summary(None) == []


# --- in the pipeline --------------------------------------------------------------------------

class FakeFeatures:
    def __init__(self, values):
        self.values = values

    def build(self, attempt):
        return dict(self.values)


class NoLists:
    def lookup(self, attempt):
        return []


class ExplainingModel:
    version = "fake-1"
    policy = Thresholds("policy-fake", 0.3, 0.6)

    def __init__(self, score=0.45, broken=False):
        self._score, self.broken = score, broken

    def score(self, features):
        return self._score

    def explain(self, features):
        if self.broken:
            raise RuntimeError("explainer broke")
        return -2.0, {"card_attempts_10m": 1.5, "amount_cents": -0.2}


def attempt(amount=1_000):
    return Attempt(attempt_id="pay_x", merchant_id="mer_x", amount_cents=amount,
                   card_fingerprint="f" * 64, occurred_at=datetime.now(UTC))


def pipeline(model, features=None):
    return Pipeline(features=FakeFeatures(features or {"card_attempts_10m": 3.0}),
                    lists=NoLists(), rules=Rules(), model=model)


def test_pipeline_records_the_model_explanation():
    decision = pipeline(ExplainingModel()).screen(attempt())
    assert decision.outcome is Outcome.VERIFY
    why = decision.explanation
    assert why["method"] == "tree-shap"
    assert why["factors"][0] == {
        "source": "model", "feature": "card_attempts_10m", "value": 3.0, "effect": 1.5,
        "direction": "raises", "text": "3 earlier tries with this card in the last 10 minutes",
        "area": "Unusual activity on this card"}


def test_stub_model_gets_the_rule_part_only():
    decision = pipeline(StubModel()).screen(attempt(amount=60_000))
    assert decision.outcome is Outcome.VERIFY
    assert decision.explanation["method"] == "rules-only"
    assert decision.explanation["factors"][0]["code"] == "high_amount"
    assert decision.explanation["factors"][0]["text"] == (
        "Rule high_amount: Amount > S$500.00 (was S$600.00)")


def test_a_broken_explainer_never_changes_the_decision():
    decision = pipeline(ExplainingModel(broken=True)).screen(attempt())
    assert decision.outcome is Outcome.VERIFY and decision.score == 0.45
    assert decision.explanation == {}


def test_explaining_stays_inside_the_screening_budget(small_model):
    """NFR-PER-02: the explanation runs inside the timed screening; it must be cheap."""
    import time

    explainer = TreeShapExplainer(small_model, NAMES)
    row = dict(zip(NAMES, [0.1, -0.2, 0.3, 0.4], strict=True))
    started = time.perf_counter()
    for _ in range(50):
        explainer.contributions(row)
    assert (time.perf_counter() - started) / 50 * 1000 < 20
