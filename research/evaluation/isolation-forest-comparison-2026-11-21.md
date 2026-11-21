# Isolation Forest vs the current fraud model (offline, 21 Nov 2026)

**Question.** Would an Isolation Forest help the gateway's fraud model (`hgb-fs02-2026-11-13`)?

**Answer: not on the data and features we have.** On its own the Isolation Forest does worse
than random guessing. As an extra feature for the HGB it adds about 2 fraud payments caught per
1,745 at the block line (+0.14 points of recall), while blocking slightly more genuine payments
than the 0.1% target. That gain is inside the noise. It costs about 2.5 ms per payment. The
recommendation is to **keep the live model as it is**. Nothing in the gateway, the deployment or
the URS was changed by this experiment.

Script: [`research/experiments/isolation_forest_comparison.py`](../experiments/isolation_forest_comparison.py).
Raw numbers: [`isolation-forest-comparison-2026-11-21.json`](isolation-forest-comparison-2026-11-21.json).

## How an Isolation Forest works (the "trees with random splits")

Picture every payment as a dot on a big table. Each dot sits in a spot set by its numbers:
how much it was for, how many times the card was used today, how long since the card's last
payment, and so on.

Now play a cutting game:

1. Pick one of those numbers at random (say, amount).
2. Pick a random place along it (say, S$740) and cut the table in two there.
3. Keep doing this to each piece, with a new random number and a new random place each time,
   until every dot is alone in its own piece.

A normal payment sits in a crowd of similar payments, so it takes many cuts before it is
finally on its own. A strange payment (S$9,000 on a card that has only ever bought coffee)
sits far away from the crowd, so one or two lucky cuts already separate it.

One round of that game, written down as a tree of cuts, is one **tree**. Because the cuts are
random, one tree can be unlucky, so the **forest** plays the game a few hundred times, each on
a small random sample of the payments (that is the "growing each tree with random points" part).
A payment's score is the average number of cuts it needed: **fewer cuts = more unusual**.

The important limit: the forest never sees which payments were fraud. It finds *unusual*
payments, not *fraudulent* ones. That only helps if fraud looks rare and odd in the numbers
we give it. On our data it does not (see "Why it fails here").

## What was compared

All three use the same 9 fs-0.2 features, the same IEEE-CIS rows (days 0-146 only; the fraud
experiment's final period, days 147+, is refused by the script) and the same time splits as the
live model: fit on days 0-110 (383,118 payments), choose settings and thresholds on days 111-128
(56,900), report on days 129-146 (47,819, of which 1,745 fraud).

| | Scorer | Details |
| --- | --- | --- |
| (a) | Current HGB | Same training code and setting as `hgb-fs02-2026-11-13`; reproduces its published numbers exactly |
| (b) | Isolation Forest alone | 8 settings tried (100/300 trees, 256/4,096 samples per tree, trained on all or genuine-only payments), best by tune-day average precision: 100 trees, 256 samples, genuine-only. Repeated with 5 random seeds |
| (c) | HGB + Isolation Forest score | The forest's score from (b) added as a 10th feature, HGB retrained with the same setting choice. 5 seeds |

The block threshold is set where 0.1% of genuine payments on the tune days would be blocked, as
the live policy is, and then applied unchanged to the report days. "Verify" is the 2% line.

## Results (report days 129-146)

| Measure | (a) Current HGB | (b) Isolation Forest | (c) HGB + IF score |
| --- | ---: | ---: | ---: |
| **Recall at the 0.1% block line** | **1.43%** (25 of 1,745) | 0.10% (0.06-0.17%) | 1.57% (1.09-1.83%) |
| False-positive rate at that line | 0.10% | 0.10% | 0.12% (0.10-0.13%) |
| Recall at the 2% verify line | 7.16% | 2.64% | 7.67% (6.36-8.71%) |
| **PR-AUC** (average precision; random = 3.65%) | **0.099** | 0.036 (0.035-0.036) | 0.102 (0.098-0.104) |
| ROC-AUC (random = 0.50) | 0.738 | 0.439 | 0.739 |
| Model call, one payment, p95 | 2.6 ms | 3.0 ms | 5.1 ms |

(b) and (c) show the mean of 5 seeds, with the lowest and highest seed in brackets.

**Uncertainty.** Fraud comes in bursts, so the 95% intervals resample whole report days
(2,000 resamples). For (c) minus (a), the recall difference at the block line has an interval
that includes zero for 3 of 5 seeds; one seed is reliably better (+0.06 to +0.76 points) and
one is reliably *worse* (-0.69 to -0.05 points). So the sign of the gain depends on the forest's
random seed. The PR-AUC difference includes zero for 3 of 5 seeds and is small (at most +0.005). For (b) minus (a), both are reliably worse
(recall -2.0 to -0.6 points, PR-AUC -0.078 to -0.051).

**Latency.** These are model calls only, one row at a time on one CPU thread (as the gateway
scores). Adding the forest costs about 2.5 ms at p95. The live screening p95 is 31 ms against
a 200 ms budget, so latency is not the problem. The weak gain is.

## Why it fails here

The Isolation Forest's ROC-AUC is below 0.5, so on these features fraud looks *more normal*
than genuine payments, not less. The reason is in the data:

* 36% of fraud payments in the report days have no usable card key (card1 or addr1 missing),
  against 9% of genuine ones. 41% of fraud has no earlier attempt on its card key, against 17%.
* Every one of those payments has the same history values (0 attempts, -1 for "no earlier
  attempt", 0 mean). That makes a dense crowd of identical dots, which is the *hardest* place
  for random cuts to isolate anything. So the forest calls them normal, and most fraud is in
  that crowd.
* The HGB already learns "no card history" as a risk signal from the labels, so the forest's
  score adds little it did not already know.

This matches the M4 write-up finding that most of the signal sits in the missing-card-key rows.

## When it could be worth another look

* With richer, more varied features (product code, card type, email domain, device, IP), where
  fraud is more likely to be the odd one out. That needs a feature-schema change first.
* As a monitoring tool rather than a blocker: flag unusual *merchant* or *traffic* patterns for
  an analyst (for example a sudden shift in a merchant's amounts), where there are no fraud labels
  to train on. That is a different use from the payment model.

## Limits

* Development data, one report window of 18 days, IEEE-CIS mapped to our schema (USD read as
  SGD cents, card key is a proxy). Not a claim about real fraud rates.
* The final period (days 147+) is consumed and was not used. These results do not replace the
  M4 fraud experiment; they are a side study for Noppawut (fraud experiment owner) to review.
* scikit-learn 1.7.2, same as the gateway.

## Reproduce

```bash
pip install -r research/requirements.txt
python research/experiments/isolation_forest_comparison.py \
  --data <fyp/03-data/derived/ieee-cis-gateway-cut-days0-146.csv.gz> \
  --out research/evaluation/isolation-forest-comparison-2026-11-21.json
```

About 10 minutes on 4 CPUs. The data cut stays on the team's machine and is not committed.
