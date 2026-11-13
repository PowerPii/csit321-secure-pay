# Fraud research (offline)

Training environment. Never deployed; it only produces versioned model artifacts.

| Folder | What |
| --- | --- |
| `notebooks/` | Exploration and experiment notebooks |
| `features/` | `gateway_schema.py`: the gateway's screening features (fs-0.2) replayed over events in plain Python, the twin of the SQL in `gateway/apps/risk/features.py`. `gateway/apps/risk/test_parity.py` replays one event stream through both and requires the same values. |
| `training/` | `train_gateway_model.py` (the model the gateway runs: IEEE-CIS days 0-146 mapped to fs-0.2, chronological split, HGB, policy thresholds) and `package_model.py` (writes the artefact + manifest) |
| `evaluation/` | Result files per accepted run (metrics, thresholds, latency), e.g. `hgb-fs02-2026-11-13.md` |
| `data/` | Local working copies / Parquet conversions. Raw IEEE-CIS CSVs stay in `../../03-data/ieee-cis/`. Git-ignored. |
| `artifacts/<version>/` | `model.joblib` + `manifest.json` (SHA-256, feature schema version, scikit-learn version, threshold policy). Git-ignored. |

Keep scikit-learn pinned to the same version as the gateway (`gateway/pyproject.toml`), since joblib artifacts don't load across versions.

The research question itself (does earlier activity help?) is studied in the team folder's
`02-research/fraud-experiment`, with its own protocol. Its final period (days 147+) was evaluated
once on 13 Nov 2026 and is consumed; nothing here reads it.

```bash
# from the repo root
python3.12 -m venv .venv && . .venv/bin/activate && pip install -r research/requirements.txt
python research/training/train_gateway_model.py --data <cut of train_transaction.csv, days 0-146>
```

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
jupyter lab
```
