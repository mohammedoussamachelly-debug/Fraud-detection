# SentinelAI — ML Pipeline

Status: **implemented and trained on the real PaySim dataset.** The user
supplied it directly (`ml/archive/PS_20174392719_1491204439457_log.csv`,
symlinked to `ml/data/paysim.csv`); see `docs/model-evaluation.md` for the
real, measured metrics and §6 below for a scalability bug this run
surfaced and fixed. The pipeline was initially validated against a
synthetic fixture before the real file was available — those numbers are
kept in `docs/model-evaluation.md` §8 purely as a labeled before/after
reference, not as a second real measurement.

## 1. Architecture recap

Per `docs/architecture.md` §5, training and inference are separate code
paths that never share a runtime:

- **Training** (`ml/training/train.py`) — offline, run as a script, reads
  a chronological split of the data, fits all three candidate models, and
  writes a versioned artifact.
- **Inference** (`backend/app/ml/inference.py`) — loads the frozen
  artifact and scores one transaction per request, inside the FastAPI
  process. It never trains, never touches `ground_truth`, and never uses
  the `ml_trainer` DB role.

Both call the same feature-engineering function — see
`docs/feature-engineering.md`.

## 2. Repository layout

```
ml/
├── requirements.txt          # mirrors backend's ML deps for a standalone ml/.venv (see §5)
├── pyproject.toml            # ruff + pytest + mypy config for this package
├── data/
│   ├── schema.py              # PaySim column/type/value validation
│   ├── loader.py               # chunked CSV read, cleaning, data-quality report, class-distribution plot
│   ├── synthetic.py            # deterministic synthetic PaySim-shaped fixture generator
│   ├── identifiers.py           # the one place that derives a stable transaction id from a CSV row
│   ├── replay.py               # POSTs cleaned rows to /transactions/ingest in step order
│   └── load_ground_truth.py     # admin-credentialed loader for ground_truth.transaction_labels
├── training/
│   ├── historical_features.py   # bulk, chronologically-correct history aggregates
│   ├── split.py                  # chronological train/val/test split + integrity check
│   ├── pipeline.py                # preprocessing + the 3 candidate model pipelines
│   ├── evaluate.py                 # metrics + validation-only threshold tuning
│   └── train.py                    # orchestrates all of the above, writes the artifact
├── explain/
│   └── shap_explainer.py        # background sample + additivity sanity check
└── tests/                     # see §7
```

`backend/app/ml/` holds the two things inference needs that training also
needs identically (`features.py`) or that are purely inference-side
(`inference.py` — artifact loading/caching, `explain.py` — SHAP contribution
mapping).

## 3. How to obtain PaySim

The real dataset ("Synthetic Financial Datasets For Fraud Detection", a.k.a.
PaySim) is public on Kaggle. This project's copy was supplied directly by
the user rather than downloaded by the pipeline:

1. Download `PS_20174392719_1491204439457_log.csv` (~470MB, ~493MB
   uncompressed) from Kaggle.
2. Place it at `ml/data/paysim.csv` (or pass `--csv <path>` to the scripts
   below) — in this repo it lives at `ml/archive/PS_20174392719_1491204439457_log.csv`
   with `ml/data/paysim.csv` symlinked to it, to avoid a second ~470MB copy.

Neither `ml/archive/` nor `ml/data/paysim.csv` is committed (`.gitignore`)
— anyone cloning this repo needs to supply the file themselves via the
steps above.

If it isn't available, every script and test here works against
`ml.data.synthetic.generate_synthetic_paysim` instead (`--synthetic` flag),
clearly labeled as synthetic wherever it's used.

## 4. How to train a model

From the repo root, using the shared venv (`backend/.venv` — see §5):

```bash
# Real PaySim (what actually produced docs/model-evaluation.md's numbers —
# 6.36M rows, ~172s end-to-end on this machine's 16 cores / 31GB RAM):
PYTHONPATH=backend backend/.venv/bin/python -m ml.training.train --csv ml/data/paysim.csv

# Synthetic fixture (fast; useful for iterating on the pipeline itself):
PYTHONPATH=backend backend/.venv/bin/python -m ml.training.train --synthetic
```

This writes `ml/artifacts/<version_label>/{model.joblib, metadata.json,
shap_background.joblib, data_quality_report.json, class_distribution.png}`
and updates `ml/artifacts/active_version.txt` to point at the new version —
which is what `backend/app/ml/inference.py` reads to decide which artifact
to serve.

## 5. Why ml/ and backend/ share one virtualenv here

`docs/architecture.md`'s "separate training from inference" requirement is
about **runtime/credentials** (training never runs inside the API process,
never uses the `api_service` role) — it does not require separate Python
environments. This project's dev machine had under 200MB of disk free at
the start of this phase (see §6), so installing XGBoost/SHAP/pandas twice
(once for a dedicated `ml/.venv`, once for `backend/.venv`) would have
roughly doubled an already-tight footprint for no architectural benefit.
`ml/requirements.txt` still exists and mirrors the exact versions, so a
dedicated `ml/.venv` can be created identically if that separation is ever
needed (e.g. a real `ml-train` container — see §6).

Both packages' tests/imports resolve across this split via each
`pyproject.toml`'s `pythonpath` setting (`ml/pyproject.toml` adds `backend/`
to its path; `backend/pyproject.toml` adds the repo root to its path) —
not via a package install. Scripts run directly (not through pytest) need
`PYTHONPATH=backend` set explicitly, as shown in the commands above.

## 6. Known limitations / deferred work

- **Real PaySim run**: see `docs/model-evaluation.md` for the actually
  measured real-data metrics (the user supplied the dataset directly —
  `ml/archive/PS_20174392719_1491204439457_log.csv`, symlinked to
  `ml/data/paysim.csv`). The synthetic-fixture numbers from before that
  point are kept in this doc's history only as a clearly labeled reference
  for how the pipeline behaved on a tiny, noisy sample — see
  `docs/model-evaluation.md` §8.

### 6.1 Resolved: a real scalability bug in `compute_historical_features`

While validating against the real dataset, `ml/training/historical_features.py`
turned out to not scale to PaySim's actual structure. The function's first
implementation computed each sender's history by iterating
`for _, group in df.groupby("nameOrig"): ...` and building one small
pandas DataFrame per sender. That's fine against `ml/tests`' small
fixtures and even against a synthetic 6.3M-row dataset built with 50,000
*reused* customers (43.5s) — but real PaySim has **6,353,307 unique
senders for 6,362,620 transactions** (mean ~1.0 transactions per sender,
not ~126). At that cardinality, the per-sender-DataFrame approach had to
allocate well over six million small Python/pandas objects: after 27+
minutes it had consumed 28 of 31GB of RAM and was still running, with no
sign of finishing — it was killed rather than risk an OOM.

**Fix**: rewrote `compute_historical_features` to use only pandas'
grouped C-level operations — `groupby(...).cumsum()` for per-sender
running totals, a `merge` for broadcasting per-`(sender, step)` block
results back to rows, and a grouped `merge_asof` for the sliding
recent-transaction window — with no per-group Python object allocation at
any point. Re-verified against the exact hand-constructed scenario in
`ml/tests/test_historical_features.py` (unchanged, still passing) and the
SQL-vs-pandas cross-check in `backend/tests/test_feature_consistency.py`
(also unchanged, still passing) before trusting it at scale. Measured
result on the full real dataset: **91.2 seconds, 6.4GB peak RSS** — down
from "still running after 27 minutes, 28GB and climbing."

This was caught specifically by testing against the real dataset's actual
sender-cardinality structure, not just a same-row-count synthetic stand-in
— a reminder that a synthetic fixture can hide a scalability bug that only
shows up against a real dataset's actual shape, not just its size.

### 6.2 Other known limitations / deferred work

- **No `ml-train` Compose service.** `docs/architecture.md` §8 describes a
  job-style `ml-train` container. Building one now would need its own
  Docker image (another xgboost/shap/pandas install, this time baked into
  an image layer) purely to demonstrate something the local venv path
  already does — deferred rather than spending more of the same
  constrained disk on a second copy of the same dependencies for no new
  capability. `infra/docker-compose.yml`'s `backend` service *does* mount
  `ml/artifacts/` read-only and point `ML_ARTIFACTS_DIR` at it, so the
  containerized API can serve whatever a locally-run training script
  produces.
- **No `risk_scores`/`alerts` persistence.** `POST /risk/score` is
  intentionally stateless (see `docs/api-contracts.md` §4.1) — it doesn't
  write a `risk_scores` row or raise an `alert`. Those tables and
  `/scoring/batch-score` belong to a later phase (Phase 5, per
  `docs/implementation-plan.md`) that also needs case/alert management
  context this phase didn't build.
- **No auth on `/risk/score` or `/transactions/ingest`.** Phase 1 never
  implemented JWT auth, so these `service`-role endpoints (per
  `docs/api-contracts.md`) currently accept unauthenticated requests. Not
  a regression introduced here — just not yet built.

### 6.3 Leakage audit

Before training on real data, the full leakage-prevention surface was
re-reviewed against seven specific concerns: chronological split
correctness, same-step (same simulated hour) handling, training/inference
feature consistency, post-transaction balance leakage, historical-feature
availability/off-by-one errors, ground-truth separation, and
target-derived features. **No leakage weakness was found** — all seven
are backed by the code (strict `step <` filters throughout, a shared
`engineer_features` function, `FORBIDDEN_FEATURE_COLUMNS` asserted in
tests, DB-level `ground_truth` isolation) and by existing targeted tests.

The audit did surface one real (non-leakage) robustness gap:
`ml/training/split.compute_split_boundaries` could, at a very small number
of unique `step` values (e.g. exactly 3, with the default 70/15/15
fractions), silently hand back a split with an *empty* validation set —
the "leave room for test" clamp could undercut the "leave room for
validation" floor. Fixed with an explicit check that raises instead of
returning a degenerate split, with a regression test
(`ml/tests/test_split.py::test_minimal_three_unique_steps_raises_rather_than_collapsing_validation`).
Real PaySim's 743 unique steps never came close to triggering this, but it
was a real gap in the function's contract worth closing regardless.

## 7. Tests

`ml/tests/` (44 tests, no DB dependency, run via `pytest` from `ml/`) covers
schema validation, the loader's cleaning policy, the synthetic generator,
the chronological split (including a deliberately-broken case and a
small-`n` edge case — see §6.3), the historical-feature aggregates against
a hand-constructed scenario with known expected values, the leakage guard,
and an end-to-end training smoke test (tmp-dir artifacts, never writing
into the real `ml/artifacts/`).

`backend/tests/` adds the DB-dependent half: ingestion idempotency, the
SQL-based history lookup, a direct cross-check that the SQL path and the
bulk-pandas training path agree on the same scenario
(`test_feature_consistency.py`), the `/risk/score` endpoint (missing model
→ 503, malformed request → 422, valid request → score + SHAP), and the
ground-truth isolation grants against live role credentials.
