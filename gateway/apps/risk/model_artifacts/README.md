# Model artifacts

Trained fraud models are copied here from `research/artifacts/<version>/`. Artefacts are
git-ignored. Until one is installed the gateway uses `StubModel` (`stub-0`, score 0), so the
rules alone decide and every decision record says `stub-0`.

## The current model

`hgb-fs02-2026-11-13` (sprint 7): HistGradientBoosting on IEEE-CIS days 0-146 mapped to schema
fs-0.2, SHA-256 `a7dee1a5216750205b2c731ac7d5874a3ec0f5e1f72c17b57ebddd770e41ec5e`. Results,
limits and the latency check: `research/evaluation/hgb-fs02-2026-11-13.md`. The artefact is not
in git (it is derived from the competition data); a copy is in the team folder under
`02-research/gateway-model/`, or rebuild it (same bytes, same hash):

```bash
python research/training/train_gateway_model.py --data <ieee-cis cut, days 0-146> \
  --version hgb-fs02-2026-11-13
```

## Installing one

1. In `research/`, train with the same scikit-learn as `gateway/pyproject.toml` (1.7.x) and
   only with features listed in `gateway/apps/risk/features.py` (`FEATURE_NAMES`). Build the
   training features with `research/features/gateway_schema.py`, the offline twin of the
   gateway's SQL features (`apps/risk/test_parity.py` keeps them equal). Write the artefact
   with `research/training/package_model.py`.
2. Copy `research/artifacts/<version>/` to `RISK_MODEL_DIR/<version>/` (this folder by default;
   the Compose stack mounts it read-only into the gateway).
3. Set `RISK_MODEL_VERSION=<version>` (optionally `RISK_MODEL_SHA256=<hash>` to pin it) and
   restart the gateway. With Compose, put the line in `deploy/.env`:
   `echo RISK_MODEL_VERSION=hgb-fs02-2026-11-13 > deploy/.env`, then
   `docker compose -f deploy/compose.yaml up -d gateway`. Each payment's fraud decision in the
   dashboard then shows the model and policy versions.
4. Check latency: `docker compose -f deploy/compose.yaml exec gateway python manage.py
   loadtest_screening` (20 screenings a second for 60 s; PASS needs p95 <= 200 ms).

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
  "feature_schema_version": "fs-0.2",
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
| `feature_schema_version` | Must be one of `COMPATIBLE_SCHEMAS` (fs-0.1, fs-0.2: each schema only adds features) |
| `features` | Column order for `predict_proba`; every name must be in `FEATURE_NAMES` |
| `policy` | Optional. Thresholds chosen on validation data; replaces `policy-0.1` (verify 0.5, block 0.9) |

The score is `predict_proba(...)[:, positive_class]`. Policy: rule block, or score at or above
`block_threshold`, blocks; a rule verify, or score at or above `verify_threshold`, asks for a
verification code; otherwise allow.
