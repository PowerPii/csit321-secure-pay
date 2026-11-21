"""Offline experiment: does an Isolation Forest help the gateway's fraud model?

    python research/experiments/isolation_forest_comparison.py --data <cut.csv[.gz]> \
        [--out research/evaluation/isolation-forest-comparison-2026-11-21.json]

Compares three scorers on the same data, features and time splits as the live model
(research/training/train_gateway_model.py, hgb-fs02-2026-11-13):

    (a) hgb         the current HistGradientBoosting model on the 9 fs-0.2 features
    (b) iforest     an Isolation Forest alone (unsupervised: never sees the fraud labels);
                    its score is "how few random cuts it took to isolate this payment"
    (c) hgb+iforest the HGB with the Isolation Forest score added as a 10th feature

Data: IEEE-CIS train_transaction days 0-146 only. The script refuses rows at day 147 or later
(the fraud experiment's final period, already consumed). Splits: fit days 0-110, tune days
111-128 (settings and thresholds), report days 129-146 (seen by nothing else).

Reported on the report days: PR-AUC (average precision), ROC-AUC, recall and false-positive
rate at the block threshold (set at 0.1% of genuine payments on the tune days, as the live
policy is), the same at the 2% verify line, a day-block bootstrap interval for the difference
against (a), and single-payment scoring latency (one row at a time, one CPU thread, as the
gateway scores). This is research only: it writes no model artefact and changes nothing the
gateway runs.
"""
from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")  # as the gateway sets it; before numpy/sklearn

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest
from sklearn.metrics import average_precision_score, roc_auc_score

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from research.training.train_gateway_model import (  # noqa: E402  same protocol as the live model
    BLOCK_FPR, DAY, MODEL_FEATURES, SETTINGS, TRAIN_END, TUNE_END, VERIFY_FPR, load,
    operating_point, threshold_at_fpr,
)

IF_GRID = {  # chosen by average precision on the tune days, like the HGB settings
    "if-100-256": {"n_estimators": 100, "max_samples": 256},
    "if-300-256": {"n_estimators": 300, "max_samples": 256},
    "if-100-4096": {"n_estimators": 100, "max_samples": 4096},
    "if-300-4096": {"n_estimators": 300, "max_samples": 4096},
}
SEEDS = (0, 1, 2, 3, 4)  # the Isolation Forest is random: repeat it to see how much that matters
BOOTSTRAP = 2000
LATENCY_ROWS = 2000


def isolation_score(forest: IsolationForest, x: np.ndarray) -> np.ndarray:
    """Higher = more unusual (isolated in fewer cuts). score_samples is the negative of that."""
    return -forest.score_samples(x)


def fit_forest(x_fit, setting: dict, seed: int, train_on: np.ndarray | None = None):
    forest = IsolationForest(random_state=seed, n_jobs=1, **setting)
    forest.fit(x_fit if train_on is None else x_fit[train_on])
    return forest


def fit_hgb(x_fit, y_fit, x_tune, y_tune):
    """Same selection as train_gateway_model.py: both settings, keep the better tune AP."""
    best = None
    for name, settings in SETTINGS.items():
        model = HistGradientBoostingClassifier(early_stopping=False, random_state=42, **settings)
        model.fit(x_fit, y_fit)
        ap = average_precision_score(y_tune, model.predict_proba(x_tune)[:, 1])
        if best is None or ap > best[0]:
            best = (ap, name, model)
    return best[2], best[1], float(best[0])


def evaluate(y_tune, s_tune, y_rep, s_rep) -> dict:
    verify_t = threshold_at_fpr(y_tune, s_tune, VERIFY_FPR)
    block_t = max(threshold_at_fpr(y_tune, s_tune, BLOCK_FPR), verify_t)
    # Diagnostic only: the best possible recall at exactly 0.1% FPR if the threshold could be
    # set on the report days themselves (it cannot in production).
    oracle_t = threshold_at_fpr(y_rep, s_rep, BLOCK_FPR)
    return {
        "tune_average_precision": round(float(average_precision_score(y_tune, s_tune)), 4),
        "pr_auc": round(float(average_precision_score(y_rep, s_rep)), 4),
        "roc_auc": round(float(roc_auc_score(y_rep, s_rep)), 4),
        "block_0_1pct": _round(operating_point(y_rep, s_rep, block_t)),
        "verify_2pct": _round(operating_point(y_rep, s_rep, verify_t)),
        "recall_at_exact_0_1pct_fpr_on_report": round(
            operating_point(y_rep, s_rep, oracle_t)["recall"], 4),
    }


def _round(point: dict) -> dict:
    return {k: round(v, 6 if k == "threshold" else 4) for k, v in point.items()}


def block_bootstrap(days, y, base, other, base_t, other_t, rng) -> dict:
    """Resample whole report days (fraud comes in bursts) and recompute the difference."""
    unique = np.unique(days)
    index = {d: np.flatnonzero(days == d) for d in unique}
    d_recall, d_ap = [], []
    for _ in range(BOOTSTRAP):
        pick = np.concatenate([index[d] for d in rng.choice(unique, size=len(unique))])
        yy = y[pick]
        if yy.sum() == 0:
            continue
        r_b = (base[pick][yy == 1] >= base_t).mean()
        r_o = (other[pick][yy == 1] >= other_t).mean()
        d_recall.append(r_o - r_b)
        d_ap.append(average_precision_score(yy, other[pick]) - average_precision_score(yy, base[pick]))
    q = lambda v: [round(float(np.percentile(v, 2.5)), 4), round(float(np.percentile(v, 97.5)), 4)]
    return {"recall_at_block_diff_95ci": q(d_recall), "pr_auc_diff_95ci": q(d_ap),
            "resamples": len(d_recall), "unit": "report day"}


def latency_ms(score_one, rows: np.ndarray) -> dict:
    for i in range(50):  # warm up
        score_one(rows[i:i + 1])
    times = []
    for i in range(len(rows)):
        started = time.perf_counter()
        score_one(rows[i:i + 1])
        times.append((time.perf_counter() - started) * 1000)
    p = np.percentile(times, [50, 95, 99])
    return {"p50": round(float(p[0]), 3), "p95": round(float(p[1]), 3), "p99": round(float(p[2]), 3),
            "rows": len(rows)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path,
                        default=ROOT / "research/evaluation/isolation-forest-comparison.json")
    args = parser.parse_args()

    rows, frame = load(args.data)  # refuses day >= 147
    x = frame.to_numpy(dtype=float)
    y = rows.isFraud.to_numpy()
    t = rows.TransactionDT.to_numpy()
    fit, tune, rep = t < TRAIN_END, (t >= TRAIN_END) & (t < TUNE_END), t >= TUNE_END
    rep_days = (t[rep] // DAY).astype(int)
    rng = np.random.default_rng(2026)
    out: dict = {
        "data": "IEEE-CIS train_transaction days 0-146 (final period days 147+ not read)",
        "rows": {"fit": int(fit.sum()), "tune": int(tune.sum()), "report": int(rep.sum())},
        "fraud_rate": {"fit": round(float(y[fit].mean()), 4), "report": round(float(y[rep].mean()), 4)},
        "features": MODEL_FEATURES, "sklearn": sklearn.__version__,
    }

    # (a) current HGB
    hgb, hgb_setting, _ = fit_hgb(x[fit], y[fit], x[tune], y[tune])
    a_tune, a_rep = hgb.predict_proba(x[tune])[:, 1], hgb.predict_proba(x[rep])[:, 1]
    out["a_hgb"] = {"setting": hgb_setting, **evaluate(y[tune], a_tune, y[rep], a_rep)}
    a_block = out["a_hgb"]["block_0_1pct"]["threshold"]
    print("(a)", json.dumps(out["a_hgb"]), flush=True)

    # (b) Isolation Forest alone: pick a setting on tune AP (seed 0), then repeat over seeds.
    grid = {}
    for name, setting in IF_GRID.items():
        for train_on, label in ((None, "all"), (y[fit] == 0, "genuine-only")):
            forest = fit_forest(x[fit], setting, 0, train_on)
            grid[f"{name}/{label}"] = round(float(average_precision_score(
                y[tune], isolation_score(forest, x[tune]))), 4)
            print("IF grid", name, label, grid[f"{name}/{label}"], flush=True)
    best_if = max(grid, key=grid.get)
    if_name, if_train = best_if.split("/")
    if_mask = None if if_train == "all" else (y[fit] == 0)
    out["iforest_grid_tune_ap"] = grid
    out["iforest_setting"] = {"name": if_name, "fit_on": if_train, **IF_GRID[if_name]}

    b_runs, c_runs, keep = [], [], {}
    for seed in SEEDS:
        forest = fit_forest(x[fit], IF_GRID[if_name], seed, if_mask)
        s = {k: isolation_score(forest, x[m]) for k, m in (("fit", fit), ("tune", tune), ("rep", rep))}
        b = evaluate(y[tune], s["tune"], y[rep], s["rep"])
        b_runs.append({"seed": seed, **b})
        # (c) HGB with the isolation score as a 10th feature (the forest never saw labels, so
        # scoring the fit rows with it does not leak fraud labels into the HGB).
        add = lambda m, k: np.column_stack([x[m], s[k]])
        hgb_c, c_setting, _ = fit_hgb(add(fit, "fit"), y[fit], add(tune, "tune"), y[tune])
        c_tune, c_rep = hgb_c.predict_proba(add(tune, "tune"))[:, 1], hgb_c.predict_proba(add(rep, "rep"))[:, 1]
        c = evaluate(y[tune], c_tune, y[rep], c_rep)
        c["bootstrap_vs_a"] = block_bootstrap(rep_days, y[rep], a_rep, c_rep, a_block,
                                              c["block_0_1pct"]["threshold"], rng)
        c_runs.append({"seed": seed, "setting": c_setting, **c})
        print("seed", seed, "(b)", b["pr_auc"], b["block_0_1pct"]["recall"],
              "(c)", c["pr_auc"], c["block_0_1pct"]["recall"], flush=True)
        if seed == SEEDS[0]:
            keep = {"forest": forest, "hgb_c": hgb_c, "b_rep": s["rep"], "b_block": b["block_0_1pct"]["threshold"]}
    keep["b_bootstrap"] = block_bootstrap(rep_days, y[rep], a_rep, keep["b_rep"], a_block,
                                          keep["b_block"], rng)

    def spread(runs, key, sub=None):
        v = [r[key][sub] if sub else r[key] for r in runs]
        return {"mean": round(float(np.mean(v)), 4), "min": round(float(min(v)), 4),
                "max": round(float(max(v)), 4)}

    for label, runs in (("b_iforest", b_runs), ("c_hgb_plus_iforest", c_runs)):
        out[label] = {
            "runs": runs,
            "summary": {"pr_auc": spread(runs, "pr_auc"), "roc_auc": spread(runs, "roc_auc"),
                        "recall_at_block": spread(runs, "block_0_1pct", "recall"),
                        "fpr_at_block": spread(runs, "block_0_1pct", "fpr"),
                        "recall_at_verify": spread(runs, "verify_2pct", "recall")},
        }
    out["b_iforest"]["bootstrap_vs_a_seed0"] = keep["b_bootstrap"]

    # Latency: one payment at a time, as the gateway scores it.
    sample = x[rep][np.random.default_rng(7).choice(rep.sum(), size=LATENCY_ROWS, replace=False)]
    forest, hgb_c = keep["forest"], keep["hgb_c"]
    out["latency_ms_single_row"] = {
        "a_hgb": latency_ms(lambda r: hgb.predict_proba(r), sample),
        "b_iforest": latency_ms(lambda r: forest.score_samples(r), sample),
        "c_hgb_plus_iforest": latency_ms(
            lambda r: hgb_c.predict_proba(np.column_stack([r, -forest.score_samples(r)])), sample),
        "note": "model call only, one CPU thread; the gateway adds feature SQL, rules and "
                "explanation (live p95 31 ms with the current model)",
    }
    print(json.dumps(out["latency_ms_single_row"]), flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
