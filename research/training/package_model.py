"""Write a trained classifier as an artefact the gateway will load.

    from research.training.package_model import package
    package(model, features=[...], version="hgb-2026-12-01",
            verify_threshold=0.31, block_threshold=0.86, metrics={...})

Produces research/artifacts/<version>/model.joblib and manifest.json in the format
gateway/apps/risk/model_artifacts/README.md describes. Copy that folder to the gateway's
RISK_MODEL_DIR and set RISK_MODEL_VERSION=<version>. The gateway refuses it unless the
SHA-256, the scikit-learn version and the feature schema match, so train with the same
scikit-learn as gateway/pyproject.toml and only with features from FEATURE_NAMES below.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import sklearn

# Must equal gateway/apps/risk/features.py (FEATURE_SCHEMA_VERSION, FEATURE_NAMES).
FEATURE_SCHEMA_VERSION = "fs-0.1"
FEATURE_NAMES = (
    "amount_cents", "card_attempts_10m", "card_attempts_1h", "card_attempts_24h",
    "card_blocked_24h", "card_distinct_emails_24h", "card_allowed_30d", "email_attempts_24h",
    "email_distinct_cards_24h", "ip_attempts_1h", "ip_distinct_cards_1h",
)

ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts"


def package(model, *, features: list[str], version: str, verify_threshold: float,
            block_threshold: float, metrics: dict | None = None,
            out_dir: Path = ARTIFACTS) -> Path:
    unknown = sorted(set(features) - set(FEATURE_NAMES))
    if unknown:
        raise ValueError(f"the gateway does not build these features: {unknown}")
    if not 0 <= verify_threshold <= block_threshold <= 1:
        raise ValueError("need 0 <= verify_threshold <= block_threshold <= 1")
    if not hasattr(model, "predict_proba"):
        raise ValueError("the model needs predict_proba")
    folder = out_dir / version
    folder.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, folder / "model.joblib")
    digest = hashlib.sha256((folder / "model.joblib").read_bytes()).hexdigest()
    manifest = {
        "version": version,
        "model_file": "model.joblib",
        "sha256": digest,
        "sklearn_version": sklearn.__version__,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "features": list(features),
        "positive_class": 1,
        "policy": {"version": f"policy-{version}", "verify_threshold": verify_threshold,
                   "block_threshold": block_threshold},
        "trained_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "estimator": type(model).__name__,
        "metrics": metrics or {},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return folder
