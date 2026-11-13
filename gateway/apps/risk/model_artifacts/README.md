# Model artifacts

Trained fraud models are copied here from `research/artifacts/<version>/`. Artefacts are
git-ignored. Until one is installed the gateway uses `StubModel` (`stub-0`, score 0), so the
rules alone decide and every decision record says `stub-0`.

## Installing one

1. In `research/`, train with the same scikit-learn as `gateway/pyproject.toml` (1.7.x) and
   only with features listed in `gateway/apps/risk/features.py` (`FEATURE_NAMES`, schema
   `fs-0.1`). Write it with `research/training/package_model.py`.
2. Copy `research/artifacts/<version>/` to `RISK_MODEL_DIR/<version>/` (this folder by default).
3. Set `RISK_MODEL_VERSION=<version>` (optionally `RISK_MODEL_SHA256=<hash>` to pin it) and
   restart the gateway.

If the artefact is missing or any check fails, the gateway logs why and **blocks every
payment as `screening_unavailable`** (FR-FRD-04) until it is fixed. It never falls back to
the stub silently.

## manifest.json

```json
{
  "version": "hgb-2026-12-01",
  "model_file": "model.joblib",
  "sha256": "<SHA-256 of model.joblib>",
  "sklearn_version": "1.7.2",
  "feature_schema_version": "fs-0.1",
  "features": ["amount_cents", "card_attempts_1h", "email_distinct_cards_24h"],
  "positive_class": 1,
  "policy": {"version": "policy-hgb-2026-12-01", "verify_threshold": 0.31, "block_threshold": 0.86},
  "trained_at": "2026-12-01T09:00:00Z",
  "metrics": {"validation_fpr": 0.01, "validation_recall": 0.62}
}
```

| Field | Checked by the gateway |
| --- | --- |
| `sha256` | Must equal the file's SHA-256 before `joblib.load` runs (joblib files can run code) |
| `sklearn_version` | Must equal the gateway's scikit-learn exactly |
| `feature_schema_version` | Must equal `FEATURE_SCHEMA_VERSION` |
| `features` | Column order for `predict_proba`; every name must be in `FEATURE_NAMES` |
| `policy` | Optional. Thresholds chosen on validation data; replaces `policy-0.1` (verify 0.5, block 0.9) |

The score is `predict_proba(...)[:, positive_class]`. Policy: rule block, or score at or above
`block_threshold`, blocks; a rule verify, or score at or above `verify_threshold`, asks for a
verification code; otherwise allow.
