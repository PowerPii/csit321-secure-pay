# Model card: hgb-fs02-2026-11-13

One-page summary of the fraud model the gateway runs, in the form proposed by Mitchell et al.
(2019), *Model Cards for Model Reporting*. Training and results in detail:
[`hgb-fs02-2026-11-13.md`](hgb-fs02-2026-11-13.md). The research question itself is answered by
the separate fraud experiment (owner Noppawut, team folder `02-research/fraud-experiment`, M4
write-up `02-research/m4-writeup/M4-fraud-experiment-results.md`).

| | |
| --- | --- |
| **Artefact** | `model.joblib` in `gateway/apps/risk/model_artifacts/hgb-fs02-2026-11-13/` (git-ignored; copy in the team folder `02-research/gateway-model/`). SHA-256 `a7dee1a5216750205b2c731ac7d5874a3ec0f5e1f72c17b57ebddd770e41ec5e`, checked against the manifest at start-up. Rebuilt byte for byte by `research/training/train_gateway_model.py`. |
| **Model** | scikit-learn 1.7.2 `HistGradientBoostingClassifier(max_iter=300, max_leaf_nodes=31, min_samples_leaf=50, learning_rate=0.1, l2_regularization=10)`. Policy `policy-hgb-fs02-2026-11-13`. Built 13 Nov 2026. |
| **Intended use** | Scoring simulated card payments in the SecurePay academic prototype (CSIT321, FYP-26-S4-36): demo shop, payment simulator, synthetic customers. One input to the screening pipeline, after the rules and lists and before the policy. |
| **Not for** | Real payments or real customers; claims of fraud-loss reduction; any decision without the rules and a human-reviewable decision record. It is not the experiment's benchmark model and was not tuned on the experiment's final period. |
| **Owner** | Gateway model: the team (built in sprint 7). Fraud experiment and its conclusions: Noppawut. |
| **Reviewed by** | Name: ______________________  Role: ______________________  Date: ____________ (left for the team) |

## Inputs and when each is known

The model reads 9 features of schema fs-0.2 (`gateway/apps/risk/features.py`), all computable
at the moment of screening, before the payment goes to the simulator:

| Feature | Source at decision time |
| --- | --- |
| `amount_cents` | The payment being screened |
| `card_attempts_10m`, `_1h`, `_24h`, `_7d`, `_30d` | Count of earlier screening events for the same keyed card fingerprint in `[t − w, t)`, strictly earlier, gateway-wide (all merchants) |
| `card_seconds_since_last` | Time since the card's previous screening event (−1 if none) |
| `card_mean_amount_30d`, `amount_to_card_mean_30d` | Mean of the card's earlier amounts in 30 days, and this amount relative to it |

No input depends on a later payment, on a fraud label, or on an outcome that arrives after the
decision. The SQL features and their offline twin (`research/features/gateway_schema.py`) are
kept equal by `apps/risk/test_parity.py`, including the experiment's golden vectors. Email and
IP history exist in the gateway but are not model inputs (IEEE-CIS has neither).

## Operating point

| Line | Score | Set on | Action |
| --- | ---: | --- | --- |
| Verify | ≥ 0.1136 | 2% of genuine payments on the tuning days | Ask for an emailed code |
| Block | ≥ 0.2222 | 0.1% of genuine payments on the tuning days (confirmed by Fifa, 13 Nov 2026) | Block |

Rules decide first: blocklist, 5 card attempts in 10 minutes, over S$10,000 → block; over S$500
→ verify; review list. If screening fails or takes over 500 ms the payment is blocked as
"screening unavailable" (NFR-PER-02, NFR-AVA-04).

## Evaluation population and results

IEEE-CIS `train_transaction.csv` (Vesta, real card-not-present payments, USD), days 0 to 146
only. Fit days 0–110 (383,118 rows, 3.42% fraud), tune days 111–128 (56,900), report days
129–146 (47,819), never used for fitting or thresholds. Days 147 onward belong to the
experiment and were never read.

| On report days 129–146 | Value |
| --- | ---: |
| ROC-AUC | 0.738 |
| Average precision (fraud rate about 3.5%) | 0.099 |
| Verify-or-block line: recall / false-positive rate | 7.2% / 1.84% |
| Block line: recall / false-positive rate | 1.4% / 0.10% |
| Whole pipeline (rules + model + policy): allow / verify / block | 94.08% / 5.75% / 0.17% of payments |
| Share of fraud the pipeline allowed | 87.7% |
| Screening time, 20/s for 60 s, 5,000 earlier events | p95 21.6 ms (13 Nov 2026); p95 28.1 ms in the Codex review of 19 Nov 2026 |

The experiment's benchmark (final period days ≥ 147, 102,703 rows, opened once on 13 Nov 2026)
compared a current-transaction model with one that adds combined history, on richer inputs
than the gateway has. History raised ROC-AUC (0.792 → 0.804) but lowered average precision
(0.175 → 0.162); recall at the 1% line rose 0.65 points (three-day-block 95% interval −0.39 to
+1.88), and both frozen thresholds breached the 1% false-positive cap (1.04% and 1.20%). The
result is **inconclusive**: no reliable gain from history at the required operating point.
Both the positive and the negative parts are reported.

## Why the competition winner's score answers a different question

The IEEE-CIS winners reached ROC-AUC 0.9459 on the private leaderboard. That number is not
comparable with ours, for three reasons:

1. **Metric.** ROC-AUC ranks the whole test batch. The gateway needs recall at a fixed,
   small false-positive rate (1%, and 0.1% for blocks), a single point on that curve.
2. **Information.** The winning features use the whole competition batch, training and test
   rows together, and masked Vesta C/D/V fields that already carry hidden history. A gateway
   deciding one payment knows only earlier payments and its own fields.
3. **Post-processing.** The winners averaged predictions within inferred client groups,
   using later payments of the same group. Online screening cannot wait for later payments.

A lower score under a strict "earlier information only" boundary is the honest figure for an
online gateway.

## Limitations

* **Weak model.** ROC-AUC 0.738; at the block line it catches 1.4% of fraud. The rules, not the
  model, make most verify decisions on this data.
* **Proxy card key.** Training used card1–card6 + addr1 as a stand-in for the vault's keyed
  fingerprint; it is not the same identity, and 10% of IEEE-CIS rows have no key at all.
* **Unit and meaning mismatch.** IEEE-CIS amounts are USD, read as SGD cents. IEEE-CIS
  attempts are processed transactions; the gateway counts every screening attempt, including
  blocked ones. Live scores are indicative only.
* **Labels.** IEEE-CIS labels are chargeback-based and propagated within accounts; training
  assumed every label is known with no delay. Label-delay analysis (7- and 30-day scenarios)
  is exploratory only and is not used for any claim.
* **One development run.** No interval on the gateway model's own figures; one dataset,
  one period, 2017–2018 payments.
* **No fairness analysis.** The data has no attributes about customers to test against.
* **Consumed holdout.** The experiment's final period was used once and must not be used to
  tune anything. A new effectiveness claim needs a new, independently labelled period.

## References

Mitchell, M. et al. (2019) 'Model Cards for Model Reporting', *Proceedings of FAT\* 2019*, pp.
220–229. doi:10.1145/3287560.3287596.
IEEE Computational Intelligence Society and Vesta Corporation (2019) *IEEE-CIS Fraud
Detection* (Kaggle competition data).
