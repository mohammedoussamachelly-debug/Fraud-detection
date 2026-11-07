# SentinelAI — Model Card

**Model**: `xgb-v1-20261106T142923` (XGBoost binary classifier + sklearn
preprocessing `Pipeline`), **trained on the real PaySim dataset**
(6,362,620 rows — see `docs/model-evaluation.md` §1). Artifact:
`ml/artifacts/<version_label>/` (`model.joblib`, `metadata.json`,
`shap_background.joblib`). See `docs/model-evaluation.md` for full metrics
and `docs/ml-pipeline.md` for how to reproduce or retrain.

## 1. Intended use and non-use

**Intended use**: a demonstration fraud-risk-scoring component for
SentinelAI, a portfolio project over synthetic PaySim-shaped data. Its
output (`POST /risk/score`) is a draft signal for a human analyst, never an
automated decision — see `docs/architecture.md` §4.5, "case decision
(human-in-the-loop)".

**Not intended for**: any real banking/financial decision, any real
individual's data, or any automated action without human review. This
project's core commitments (`CLAUDE.md`) prohibit real banking integration
in any environment.

## 2. Model choice

Three candidates were trained and compared (`docs/model-evaluation.md`
§3): a most-frequent-class dummy baseline, logistic regression
(class-weight balanced), and XGBoost (`scale_pos_weight` tuned to the
training split's class ratio). **XGBoost is the model actually served**,
for one specific reason: SHAP explainability in this implementation
(`backend/app/ml/explain.py`) uses `shap.TreeExplainer`, which requires a
tree-based model. This is a deliberate, documented scope decision, not a
claim that XGBoost strictly dominates the other candidates on every metric
at every threshold — see the honest comparison in
`docs/model-evaluation.md` §3, where logistic regression in fact scores
higher F1/recall at the uncalibrated 0.5 threshold on this tiny fixture.

## 3. Features and what the model never sees

Full list and rationale in `docs/feature-engineering.md`. In short: amount
(raw + log), transaction type, hour-of-day (from `step`), sender/recipient
pre-transaction balances, and four historical aggregates computed with a
strict "earlier step only" filter, plus a `sender_is_new` indicator for
accounts with no prior history.

**Never a feature, enforced by `ml/tests/test_leakage.py` and
`docs/database-design.md` §3's DB-level grants**: `isFraud`,
`isFlaggedFraud`, or either post-transaction balance
(`newbalanceOrig`/`newbalanceDest`).

## 4. SHAP explanation semantics

`backend/app/ml/explain.py` builds `shap.TreeExplainer(classifier,
data=background, model_output="probability",
feature_perturbation="interventional")`. Concretely, this means:

- `base_value` and every `shap_contribution` are in **probability units**
  (0–1), not log-odds/margin units.
- For any scored row: `base_value + sum(ALL features' contributions) ≈
  predicted fraud probability` (verified to ~1.8×10⁻⁸ error in this run —
  `docs/model-evaluation.md` §6). The API only returns the top 5 by
  magnitude by default, so summing just the returned `contributions` will
  *not* reconstruct the full score — that's expected, not a bug.
- One-hot-encoded `transaction_type` columns are summed back into a single
  `transaction_type` contribution before being returned, so the API never
  exposes raw preprocessing internals (`app/ml/explain._feature_group_map`).
- Background sample: 100 rows drawn from the **validation** split
  (`ml/explain/shap_explainer.sample_background`), saved alongside the
  model artifact — never drawn from test data, and never containing a
  ground-truth label (it's a slice of already-engineered features, which
  by construction (`app/ml/features.py`) never include one).

No explanation is ever hardcoded or LLM-generated; every contribution
returned by `POST /risk/score?include_explanation=true` is this model's
actual SHAP output for that actual request.

## 5. Threshold and risk bands

Selected threshold: **0.98** (tuned on validation data only, maximizing
F1 — see `docs/model-evaluation.md` §5 for the full rationale and
validation/test metrics at this threshold; it's high because XGBoost's
predicted probabilities on real PaySim are strongly bimodal). `risk_level`
bands
(`backend/app/ml/inference.risk_level_for_score`):

| Score | Level |
|---|---|
| `< threshold * 0.5` | `low` |
| `threshold * 0.5` ≤ score `< threshold` | `medium` |
| `≥ threshold` | `high` |

These bands are a simple, documented design choice (not a statistically
derived calibration) — a `high` alert means "at or above the F1-optimal
validation threshold," nothing more precise than that.

## 6. Known limitations

- **Real PaySim is itself a simulation**, not real banking data (by this
  project's own design — see `CLAUDE.md`). Its fraud pattern (large
  `TRANSFER`/`CASH_OUT` transactions that fully drain the sender's
  balance) is realistic but singular; a model this strong on PaySim should
  not be read as "this strong on real-world fraud typologies in general."
- **173 missed fraud cases in validation, 221 in test** at the selected
  threshold (`docs/model-evaluation.md` §5) — meaningfully better than the
  dummy/logistic baselines, but still real, non-zero missed fraud.
- **Class imbalance handled only via `scale_pos_weight`/`class_weight`**,
  not resampling — simpler and chronology-safe, but leaves headroom
  unexplored (e.g. time-aware resampling within the training window only).
- **No model monitoring/drift detection** — out of scope for this phase.
- **`risk_level` bands are a fixed multiplier of one threshold**, not a
  separately calibrated set of cutoffs.

## 7. Traceability

`metadata.json` alongside the artifact records: training/validation/test
row counts and step boundaries, the exact feature list, every
hyperparameter, the random seed (42), the full three-model comparison, the
selected threshold and its rationale, final validation/test metrics,
measured inference latency, and the SHAP additivity check's result. Any
future metric claim about this model should be traceable to that file, not
restated from memory.
