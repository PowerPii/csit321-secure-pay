"""Train the HistGradientBoosting model the gateway runs, on IEEE-CIS mapped to fs-0.2.

    python research/training/train_gateway_model.py --data <cut.csv[.gz]> [--version hgb-fs02-YYYY-MM-DD]

This is the integration build for MVP sprint 7, not the research result. The research
question (does earlier activity help?) is answered by the fraud experiment in the team's
02-research/fraud-experiment folder, with its own protocol and sealed final holdout. This
script only reuses that protocol's time splits and never reads the holdout: it refuses any
row at day 147 or later, so pass it a cut of train_transaction.csv with days 0 to 146 and the
columns TransactionID, TransactionDT, TransactionAmt, isFraud, card1-card6, addr1.

Mapping IEEE-CIS to what the gateway sees (research/features/gateway_schema.py):

    TransactionDT                -> event time (seconds)
    TransactionAmt (USD)         -> amount_cents = round(amount * 100), read as SGD cents
    card1..card6 + addr1         -> card key (a proxy for the vault's card fingerprint; empty
                                    when card1 or addr1 is missing). Not a real card identity.
    (none)                       -> email and IP keys: IEEE-CIS has neither, so email_* and
                                    ip_* features are not used by this model
    (none)                       -> screening outcomes: unknown, so card_blocked_24h and
                                    card_allowed_30d are not used by this model

Splits (days of TransactionDT): fit on days 0-110; choose the setting and the policy
thresholds on days 111-128; report on days 129-146, which neither step has seen.
Thresholds: block at the score that flags 0.1% of genuine payments on days 111-128, ask for a
verification code at 2%. The artefact goes to research/artifacts/<version>/ via
package_model.py; copy that folder to the gateway (gateway/apps/risk/model_artifacts/README.md).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.features.gateway_schema import Event, replay
from research.training.package_model import package

DAY = 86400
TRAIN_END, TUNE_END, REPORT_END = 111 * DAY, 129 * DAY, 147 * DAY  # fraud-experiment config
MODEL_FEATURES = [
    "amount_cents", "card_attempts_10m", "card_attempts_1h", "card_attempts_24h",
    "card_attempts_7d", "card_attempts_30d", "card_seconds_since_last",
    "card_mean_amount_30d", "amount_to_card_mean_30d",
]
CARD_COLUMNS = ["card1", "card2", "card3", "card4", "card5", "card6", "addr1"]
SETTINGS = {
    "baseline": {"max_iter": 100, "max_leaf_nodes": 15, "min_samples_leaf": 50,
                     "learning_rate": 0.1, "l2_regularization": 1.0},
    "regularized": {"max_iter": 300, "max_leaf_nodes": 31, "min_samples_leaf": 50,
                        "learning_rate": 0.1, "l2_regularization": 10.0},
}
VERIFY_FPR, BLOCK_FPR = 0.02, 0.001


def card_key(row) -> str:
    if pd.isna(row.card1) or pd.isna(row.addr1):
        return ""
    return "|".join("" if pd.isna(v) else str(v) for v in (getattr(row, c) for c in CARD_COLUMNS))


def load(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = pd.read_csv(path)
    if (rows.TransactionDT >= REPORT_END).any():
        raise SystemExit("rows at day 147 or later found: the final holdout must stay sealed")
    if rows.TransactionID.duplicated().any():
        raise SystemExit("duplicate TransactionID")
    rows = rows.sort_values(["TransactionDT", "TransactionID"], kind="stable").reset_index(drop=True)
    events = [Event(at=float(r.TransactionDT), amount_cents=round(r.TransactionAmt * 100),
                    card=card_key(r)) for r in rows.itertuples(index=False)]
    started = time.perf_counter()
    x = pd.DataFrame(replay(events))[MODEL_FEATURES]
    print(f"replayed {len(events):,} events in {time.perf_counter() - started:.0f} s", flush=True)
    return rows, x


def threshold_at_fpr(y, scores, fpr) -> float:
    """Lowest threshold whose share of flagged genuine payments (score >= t) is <= fpr."""
    negatives = np.sort(scores[y == 0])[::-1]
    allowed = int(np.floor(fpr * len(negatives)))
    if allowed >= len(negatives):
        return 0.0
    return float(np.nextafter(negatives[allowed], 1.0))  # just above the first one not allowed


def operating_point(y, scores, t) -> dict:
    flagged = scores >= t
    return {"threshold": t, "recall": float(flagged[y == 1].mean()),
            "fpr": float(flagged[y == 0].mean()), "flagged_share": float(flagged.mean())}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--version", default=f"hgb-fs02-{datetime.now(UTC):%Y-%m-%d}")
    args = parser.parse_args()

    rows, frame = load(args.data)
    # Plain arrays, in MODEL_FEATURES order: the gateway scores a numpy row in manifest order.
    x = frame.to_numpy(dtype=float)
    y = rows.isFraud.to_numpy()
    t = rows.TransactionDT.to_numpy()
    fit, tune, report = t < TRAIN_END, (t >= TRAIN_END) & (t < TUNE_END), t >= TUNE_END

    trials, best = [], None
    for name, settings in SETTINGS.items():
        model = HistGradientBoostingClassifier(early_stopping=False, random_state=42, **settings)
        model.fit(x[fit], y[fit])
        ap = average_precision_score(y[tune], model.predict_proba(x[tune])[:, 1])
        trials.append({"setting": name, "tune_average_precision": round(float(ap), 4)})
        print(f"{name}: tune AP {ap:.4f}", flush=True)
        if best is None or ap > best[0]:
            best = (ap, name, model)
    _, chosen, model = best

    tune_scores = model.predict_proba(x[tune])[:, 1]
    verify_t = threshold_at_fpr(y[tune], tune_scores, VERIFY_FPR)
    block_t = max(threshold_at_fpr(y[tune], tune_scores, BLOCK_FPR), verify_t)
    report_scores = model.predict_proba(x[report])[:, 1]
    metrics = {
        "data": "IEEE-CIS train_transaction days 0-146 (final holdout days 147+ not read)",
        "rows": {"fit": int(fit.sum()), "tune": int(tune.sum()), "report": int(report.sum())},
        "fraud_rate_fit": round(float(y[fit].mean()), 4),
        "setting": chosen, "trials": trials,
        "report_days_129_146": {
            "roc_auc": round(float(roc_auc_score(y[report], report_scores)), 4),
            "average_precision": round(float(average_precision_score(y[report], report_scores)), 4),
            "verify_or_block": operating_point(y[report], report_scores, verify_t),
            "block": operating_point(y[report], report_scores, block_t),
        },
        "features_not_used": "email_*, ip_* (no such data), card_blocked_24h, card_allowed_30d "
                             "(no screening outcomes in the data)",
        "card_key": "+".join(CARD_COLUMNS),
    }
    folder = package(model, features=MODEL_FEATURES, version=args.version,
                     verify_threshold=round(verify_t, 6), block_threshold=round(block_t, 6),
                     metrics=metrics)
    print(json.dumps(metrics, indent=2))
    print(f"sklearn {sklearn.__version__}; artefact in {folder}")


if __name__ == "__main__":
    main()
