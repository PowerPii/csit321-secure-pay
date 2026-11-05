# Fraud research (offline)

Training environment. Never deployed; it only produces versioned model artifacts.

| Folder | What |
| --- | --- |
| `notebooks/` | Exploration and experiment notebooks |
| `features/` | Feature definitions, written once. Each has a pandas implementation (here) and a SQL implementation used by `gateway/apps/risk`. A parity test replays mapped historical rows through both and requires identical values. |
| `training/` | Batch scripts: chronological split, train `LogisticRegression` and `HistGradientBoostingClassifier`, pick thresholds on validation data |
| `evaluation/` | Result files per accepted run (metrics, PR curves, confusion counts, latency) |
| `data/` | Local working copies / Parquet conversions. Raw IEEE-CIS CSVs stay in `../../03-data/ieee-cis/`. Git-ignored. |
| `artifacts/<version>/` | `model.joblib` + `manifest.json` (SHA-256, feature schema version, scikit-learn version, threshold policy). Git-ignored. |

Keep scikit-learn pinned to the same version as the gateway (`gateway/pyproject.toml`), since joblib artifacts don't load across versions.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab
```
