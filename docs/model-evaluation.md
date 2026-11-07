# SentinelAI — Model Evaluation

Status: **real measured results, from the actual PaySim dataset.** Every
metric below comes from running `ml.training.train --csv
ml/data/paysim.csv` against `ml/archive/PS_20174392719_1491204439457_log.csv`
(6,362,620 rows, the full "Synthetic Financial Datasets For Fraud
Detection" PaySim export, supplied directly for this phase). §8 keeps the
small synthetic-fixture run from before this file existed, as a clearly
labeled reference only — it is not a second real measurement.

## 1. Dataset

| | |
|---|---|
| Source | `ml/archive/PS_20174392719_1491204439457_log.csv` (real PaySim) |
| Rows read | 6,362,620 |
| Rows after cleaning | 6,362,620 (0 duplicates, 0 missing values, 0 invalid types, 0 negative amounts — the real export is already clean) |
| Fraud rate | 0.1291% (8,213 fraudulent of 6,362,620) |
| Unique senders (`nameOrig`) | 6,353,307 — **mean 1.00 transactions per sender** |
| Unique recipients (`nameDest`) | 2,722,362 |
| Step range | 1–743 (743 unique steps) |
| Type distribution | CASH_OUT 2,237,500 · PAYMENT 2,151,495 · CASH_IN 1,399,284 · TRANSFER 532,909 · DEBIT 41,432 |

## 2. Why accuracy isn't reported as a headline metric

At a 0.13% fraud rate, a model predicting "legitimate" for every
transaction scores 99.87% accuracy while catching zero fraud. Accuracy is
never reported standalone anywhere in this pipeline
(`ml/training/evaluate.py`) — precision, recall, F1, average precision
(PR-AUC), ROC-AUC, false-positive rate, and false alerts per 1,000
legitimate transactions are used instead.

## 3. Chronological split

| Split | Rows | Step range |
|---|---|---|
| Train | 6,082,007 | steps 1–520 |
| Validation | 191,147 | steps 521–631 |
| Test | 89,466 | steps 632–743 |

Boundaries computed over unique `step` values (70/15/15 of 743 unique
steps), never row counts (`ml/training/split.py`).

## 4. Model comparison (validation set, threshold 0.5)

| Model | Precision | Recall | F1 | Avg. Precision (PR-AUC) | ROC-AUC | False alerts / 1,000 legit |
|---|---|---|---|---|---|---|
| Dummy baseline (most-frequent) | 0.000 | 0.000 | 0.000 | 0.006 | 0.500 | 0.0 |
| Logistic Regression (class-weight balanced) | 0.079 | 0.935 | 0.145 | 0.468 | 0.983 | 68.1 |
| **XGBoost** (served) | **0.328** | **0.999** | **0.494** | **0.949** | **0.9995** | 12.7 |

Unlike the small synthetic fixture (§8), XGBoost clearly and substantially
outperforms both baselines here — real PaySim's fraud pattern (large
`TRANSFER`/`CASH_OUT` transactions that fully drain the sender's balance)
is a genuine, learnable behavioral signal, not injected noise. At the
default 0.5 threshold XGBoost already catches 99.9% of validation fraud,
at the cost of a still-high false-alert rate — exactly what threshold
tuning (§5) exists to fix.

## 5. Threshold selection

Thresholds in `(0.01, 0.99)` are swept against **validation-set
predictions only**, maximizing F1 (`ml/training/evaluate.tune_threshold`).
The test set is scored exactly once, with this fixed threshold, as the
final step.

**Selected threshold: 0.98** — high, because XGBoost's predicted
probabilities on this data are strongly bimodal (most legitimate
transactions score near 0, most fraud scores near 1), so the F1-optimal
cutoff sits close to 1 rather than near a traditional 0.5.

| Metric | Validation (threshold tuned on this split) | Test (scored once, same threshold) |
|---|---|---|
| Precision | 0.927 | 0.961 |
| Recall | 0.853 | 0.823 |
| F1 | 0.889 | 0.887 |
| Average Precision | 0.949 | 0.961 |
| ROC-AUC | 0.9995 | 0.9992 |
| False positive rate | 0.042% | 0.048% |
| False alerts / 1,000 legitimate | 0.42 | 0.48 |
| Confusion matrix (TP/FP/TN/FN) | 1,007 / 79 / 189,888 / 173 | 1,031 / 42 / 88,172 / 221 |

Validation and test metrics are close to each other, which is a sanity
check on the split, not a guarantee of future performance on different
data. 173 (validation) and 221 (test) missed fraud cases remain — at this
threshold, roughly 15–18% of real fraud in these splits is not caught;
lowering the threshold trades some of that recall back in exchange for
materially more false alerts (see the full sweep behavior implied by the
threshold-0.5 row in §4).

## 6. Inference latency

Median single-row `predict_proba` latency over 100 repeated calls:
**2.00 ms** (`ml/training/evaluate.measure_inference_latency_ms`), measured
on the training machine's CPU, no concurrency.

## 7. SHAP additivity check

Maximum reconstruction error (`base_value + sum(all 11 features'
contributions)` vs. actual `predict_proba`) on this run: **8.0 × 10⁻⁸** —
floating-point noise, confirming the probability-space `TreeExplainer`
configuration is mathematically consistent with this model's actual
predictions (`docs/model-card.md` §3).

A live, real example (full balance-draining `TRANSFER`, a textbook PaySim
fraud shape): scored **0.989** ("high"), with `amount`, `transaction_type`,
`sender_prev_balance`, and `recipient_prev_balance` all pushing risk up —
exactly the pattern a human analyst would look for. A small legitimate
`PAYMENT` scored **3.1 × 10⁻⁶** ("low"). Both captured live from the
running backend, not fabricated.

## 8. Reference only: the earlier synthetic-fixture run

Before the real dataset was available, the pipeline was validated against
`ml.data.synthetic.generate_synthetic_paysim()` (5,000 rows, 99 fraud,
seed 42). That run is kept here **only** as a before/after reference for
how differently a tiny, randomly-injected-fraud fixture behaves — it is
not a second real measurement and should not be averaged with §4–§7.

| Metric (test set, synthetic fixture) | Value |
|---|---|
| Precision | 0.0625 |
| Recall | 0.364 |
| F1 | 0.107 |
| Average Precision | 0.069 |
| ROC-AUC | 0.820 |
| False alerts / 1,000 legit | 81.2 |

The gap between this and §4–§7 (ROC-AUC 0.82 vs. 0.9995; F1 0.11 vs. 0.89)
is itself informative: it's largely the difference between ~16 randomly-
labeled "fraud" rows with no real behavioral signal, and real PaySim's
genuine, learnable fraud pattern at a realistic scale.
