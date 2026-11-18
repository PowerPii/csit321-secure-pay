"""The model stage of screening: one interface, a stub until a trained artefact is installed.

    Model.version          recorded on every decision (FR-FRD-01)
    Model.score(features)  probability-like score in [0, 1]; may raise, which screening
                           treats as "screening unavailable" (FR-FRD-04), never as fraud
    Model.policy           optional thresholds shipped with the artefact

`StubModel` stands in until the fraud experiment hands over a HistGradientBoosting
artefact (MVP-SCOPE sprint 7). To install one, copy `research/artifacts/<version>/` to
`RISK_MODEL_DIR/<version>/` and set `RISK_MODEL_VERSION=<version>`. The folder holds
`model.joblib` and `manifest.json` (format in model_artifacts/README.md). It is loaded only
if the SHA-256, the scikit-learn version and the feature schema all match, because joblib
files run code when loaded and do not load across scikit-learn versions.
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings

from apps.risk.features import COMPATIBLE_SCHEMAS, FEATURE_NAMES, FEATURE_SCHEMA_VERSION

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Thresholds:
    version: str
    verify_threshold: float
    block_threshold: float


class Model(Protocol):
    version: str
    policy: Thresholds | None

    def score(self, features: dict[str, float]) -> float: ...


class StubModel:
    """No trained model yet: a fixed score of 0, so the rules alone decide.

    Recorded as `stub-0` on every decision so nobody mistakes it for a trained model.
    """

    version = "stub-0"
    policy = None

    def score(self, features: dict[str, float]) -> float:
        return 0.0


class UnavailableModel:
    """The configured artefact could not be loaded. Every attempt is blocked as
    screening_unavailable until it is fixed (FR-FRD-04, Fifa's decision of 5 Nov 2026)."""

    policy = None

    def __init__(self, version: str, problem: str):
        self.version = version
        self.problem = problem

    def score(self, features: dict[str, float]) -> float:
        raise RuntimeError(f"model {self.version} unavailable: {self.problem}")


class ArtifactError(Exception):
    pass


class ArtifactModel:
    """A scikit-learn classifier with `predict_proba` (HistGradientBoostingClassifier)."""

    def __init__(self, estimator: Any, manifest: dict):
        self.estimator = estimator
        self.version = manifest["version"]
        self.feature_order: list[str] = list(manifest["features"])
        classes = list(getattr(estimator, "classes_", [0, 1]))
        self.positive_index = classes.index(manifest.get("positive_class", 1))
        policy = manifest.get("policy")
        self.policy = Thresholds(
            version=policy["version"],
            verify_threshold=float(policy["verify_threshold"]),
            block_threshold=float(policy["block_threshold"]),
        ) if policy else None

        self.explainer = None
        try:
            from apps.risk.explain import TreeShapExplainer

            if self.positive_index == 1:  # contributions are towards class 1
                self.explainer = TreeShapExplainer(estimator, self.feature_order)
        except Exception:  # explanations are optional; scoring still works
            logger.exception("Risk model %s: no explanations", self.version)

    def score(self, features: dict[str, float]) -> float:
        import numpy as np

        row = np.array([[features[name] for name in self.feature_order]], dtype=float)
        return float(self.estimator.predict_proba(row)[0][self.positive_index])

    def explain(self, features: dict[str, float]) -> tuple[float, dict[str, float]] | None:
        """TreeSHAP contributions in log-odds (apps.risk.explain), or None if unsupported."""
        return self.explainer.contributions(features) if self.explainer else None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_artifact(folder: Path, expected_sha256: str = "") -> ArtifactModel:
    """Check the manifest, then load. Raises ArtifactError with a reason on any mismatch."""
    import sklearn

    try:
        manifest = json.loads((folder / "manifest.json").read_text())
    except (OSError, ValueError) as exc:
        raise ArtifactError(f"manifest.json unreadable: {exc}") from None
    for key in ("version", "sha256", "sklearn_version", "feature_schema_version", "features"):
        if key not in manifest:
            raise ArtifactError(f"manifest.json has no '{key}'")
    if manifest["feature_schema_version"] not in COMPATIBLE_SCHEMAS:
        raise ArtifactError(f"trained on feature schema {manifest['feature_schema_version']}, "
                            f"gateway builds {FEATURE_SCHEMA_VERSION} (accepts {', '.join(COMPATIBLE_SCHEMAS)})")
    unknown = sorted(set(manifest["features"]) - set(FEATURE_NAMES))
    if unknown:
        raise ArtifactError(f"needs features the gateway does not build: {unknown}")
    if manifest["sklearn_version"] != sklearn.__version__:
        raise ArtifactError(f"built with scikit-learn {manifest['sklearn_version']}, "
                            f"gateway has {sklearn.__version__}")
    model_file = folder / manifest.get("model_file", "model.joblib")
    if model_file.parent.resolve() != folder.resolve():
        raise ArtifactError("model_file must be inside the artefact folder")
    if not model_file.is_file():
        raise ArtifactError(f"{model_file.name} missing")
    actual = sha256_of(model_file)
    if actual != manifest["sha256"]:
        raise ArtifactError("SHA-256 of the model file does not match the manifest")
    if expected_sha256 and actual != expected_sha256:
        raise ArtifactError("SHA-256 does not match RISK_MODEL_SHA256")

    import joblib

    # The hash was checked against the manifest (and the optional pin) above.
    estimator = joblib.load(model_file)  # nosec B301
    if not hasattr(estimator, "predict_proba"):
        raise ArtifactError("the model has no predict_proba")
    return ArtifactModel(estimator, manifest)


@functools.cache
def active_model() -> Model:
    """The model screening uses, loaded once per process."""
    version = settings.RISK_MODEL_VERSION
    if not version:
        return StubModel()
    try:
        model = load_artifact(Path(settings.RISK_MODEL_DIR) / version,
                              settings.RISK_MODEL_SHA256)
    except ArtifactError as exc:
        logger.error("Risk model %s not loaded: %s. Screening will block every attempt.",
                     version, exc)
        return UnavailableModel(version, str(exc))
    logger.info("Risk model %s loaded", model.version)
    return model
