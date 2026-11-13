"""Loading a trained artefact: the checks that keep a wrong or tampered model out."""
import json

import joblib
import numpy as np
import pytest
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier

from apps.risk import scoring
from apps.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_VERSION
from apps.risk.pipeline import Attempt, Outcome, Pipeline

FEATURES = ["amount_cents", "card_attempts_1h", "email_distinct_cards_24h"]


@pytest.fixture(scope="module")
def estimator():
    rng = np.random.default_rng(7)
    x = rng.random((400, len(FEATURES))) * [100_000, 10, 5]
    y = (x[:, 1] > 6).astype(int)  # "many attempts" is risky
    return HistGradientBoostingClassifier(max_iter=20).fit(x, y)


@pytest.fixture
def artefact(tmp_path, estimator):
    def make(**manifest_overrides):
        folder = tmp_path / "hgb-test-1"
        folder.mkdir(exist_ok=True)
        joblib.dump(estimator, folder / "model.joblib")
        manifest = {
            "version": "hgb-test-1", "model_file": "model.joblib",
            "sha256": scoring.sha256_of(folder / "model.joblib"),
            "sklearn_version": sklearn.__version__,
            "feature_schema_version": FEATURE_SCHEMA_VERSION, "features": FEATURES,
            "positive_class": 1,
            "policy": {"version": "policy-hgb-test", "verify_threshold": 0.4,
                       "block_threshold": 0.95},
            **manifest_overrides,
        }
        (folder / "manifest.json").write_text(json.dumps(manifest))
        return folder

    return make


def features(**kw):
    return {**{n: 0.0 for n in FEATURE_NAMES}, **kw}


def test_trained_artefact_loads_and_scores(artefact):
    model = scoring.load_artifact(artefact())
    assert model.version == "hgb-test-1"
    assert model.policy.version == "policy-hgb-test"
    low = model.score(features(card_attempts_1h=1))
    high = model.score(features(card_attempts_1h=9))
    assert 0 <= low < 0.4 < high <= 1


def test_artefact_drops_into_the_pipeline(artefact, settings):
    from datetime import UTC, datetime

    model = scoring.load_artifact(artefact())

    class F:
        def build(self, attempt):
            return features(amount_cents=attempt.amount_cents, card_attempts_1h=9)

    class NoLists:
        def lookup(self, attempt):
            return []

    d = Pipeline(features=F(), lists=NoLists(), model=model).screen(Attempt(
        "pay_1", "mer_1", 1000, "fp", datetime(2026, 11, 13, tzinfo=UTC)))
    assert d.model_version == "hgb-test-1" and d.policy_version == "policy-hgb-test"
    assert d.outcome in (Outcome.VERIFY, Outcome.BLOCK)


@pytest.mark.parametrize(("override", "problem"), [
    ({"sha256": "0" * 64}, "SHA-256"),
    ({"sklearn_version": "0.0.1"}, "scikit-learn"),
    ({"feature_schema_version": "fs-9"}, "feature schema"),
    ({"features": ["amount_cents", "device_age_days"]}, "device_age_days"),
    ({"model_file": "../elsewhere.joblib"}, "inside the artefact folder"),
])
def test_wrong_artefacts_are_refused(artefact, override, problem):
    with pytest.raises(scoring.ArtifactError, match=problem):
        scoring.load_artifact(artefact(**override))


def test_pinned_hash_must_match_too(artefact):
    with pytest.raises(scoring.ArtifactError, match="RISK_MODEL_SHA256"):
        scoring.load_artifact(artefact(), expected_sha256="f" * 64)


def test_missing_artefact_makes_screening_unavailable(settings, tmp_path):
    settings.RISK_MODEL_DIR = str(tmp_path)
    settings.RISK_MODEL_VERSION = "hgb-missing"
    scoring.active_model.cache_clear()
    try:
        model = scoring.active_model()
        assert isinstance(model, scoring.UnavailableModel)
        with pytest.raises(RuntimeError):
            model.score(features())
    finally:
        scoring.active_model.cache_clear()


def test_no_version_configured_means_the_stub(settings):
    settings.RISK_MODEL_VERSION = ""
    scoring.active_model.cache_clear()
    try:
        assert scoring.active_model().version == "stub-0"
    finally:
        scoring.active_model.cache_clear()
