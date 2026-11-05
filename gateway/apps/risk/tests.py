import pytest

from apps.risk.pipeline import Attempt, Outcome, Pipeline, Rules, ScreeningUnavailable


def attempt(**kw):
    base = {"attempt_id": "a1", "merchant_id": "m1", "amount_cents": 1_000, "card_fingerprint": "fp"}
    return Attempt(**{**base, **kw})


def test_low_risk_is_allowed():
    d = Pipeline().screen(attempt())
    assert d.outcome is Outcome.ALLOW
    assert d.model_version == "stub-0"


def test_blocklisted_card_is_blocked_with_reason():
    d = Pipeline(rules=Rules(blocklisted_fingerprints=frozenset({"fp"}))).screen(attempt())
    assert d.outcome is Outcome.BLOCK
    assert "blocklisted_card" in d.reasons


def test_high_amount_requires_verification():
    assert Pipeline().screen(attempt(amount_cents=60_000)).outcome is Outcome.VERIFY


def test_model_failure_is_screening_unavailable_not_fraud():
    class Broken:
        version = "x"

        def score(self, features):
            raise RuntimeError("model not loaded")

    with pytest.raises(ScreeningUnavailable):
        Pipeline(model=Broken()).screen(attempt())


def test_features_never_hold_card_numbers():
    d = Pipeline().screen(attempt())
    assert not any("pan" in k or "card_number" in k for k in d.features)
