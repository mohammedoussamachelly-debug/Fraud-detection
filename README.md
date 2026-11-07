# SentinelAI

A portfolio-quality, AI-powered financial fraud detection and investigation
platform built on synthetic data (PaySim) only — no real banking integration.
See `CLAUDE.md` for the project vision and rules, and `docs/` for the full
architecture, database design, API contracts, and phased implementation plan.

**Current status**: Phases 1–6 complete; Phase 7 frontend implemented, with live-backend end-to-end verification pending. Phase 2's data model (`accounts`,
`transactions`, isolated `ground_truth.transaction_labels`); Phase 3 (ML
training + inference), **trained and evaluated on the real PaySim
dataset** (see `docs/model-evaluation.md` for real measured metrics);
Phase 4 (graph analytics — bounded neighborhoods, structural metrics,
fund-flow tracing, four `/graph/*` endpoints); Phase 5 (persistent risk
scores, fraud alerts, investigation cases, server-resolved evidence,
audit logging, and a minimal real JWT+bcrypt auth system — see
`docs/alerts-and-cases.md` and `docs/authentication.md`); Phase 6
(LangGraph multi-agent investigations — three agents collecting
evidence, analyzing the transaction graph, and drafting a human-
reviewed report, plus closing the Phase 1–4 authentication gap — see
`docs/multi-agent-architecture.md`, `docs/agent-tools.md`,
`docs/agent-security.md`, `docs/investigation-workflow.md`). All
verified against a real local PostgreSQL database — 167 backend tests
pass (0 failed, 0 skipped). See `docs/implementation-plan.md`'s "Current
Status" for the exact breakdown and `docs/ml-pipeline.md` for the ML
pipeline specifically, including a real scalability bug that training
run found and fixed.

**The LLM behind Phase 6's report-writing step is a deterministic mock**
in this environment — no `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` is
configured anywhere here. See `docs/agent-security.md` §1 for exactly
what that does and doesn't mean, and how to configure a real provider.

The Phase 7 dashboard includes protected login, overview, alert triage, transaction
details and SHAP explanations, accounts, case evidence/notes/decisions, network
exploration, AI report review, and an administrator audit log. See
[the user guide](docs/dashboard-user-guide.md), [design system](docs/design-system.md),
[frontend architecture](docs/frontend-architecture.md), [UX flows](docs/ux-flows.md),
and [verification record](docs/frontend-qa.md). Browser fixtures are isolated from
the application; the UI always requests the real API and never substitutes fixtures.

## Repository layout

```
backend/    FastAPI app, SQLAlchemy, Alembic migrations, pytest tests,
            app/ml/ (shared feature engineering + inference + SHAP),
            app/graph/ (NetworkX graph construction, metrics, fund-flow,
            synthetic scenarios), app/agents/ (LangGraph investigation
            workflow: node logic, read-only tools, LLM provider
            abstraction), app/services/investigations.py (orchestration)
ml/         Offline training pipeline: PaySim loading, feature engineering,
            chronological split, model training/evaluation, SHAP setup
frontend/   React + TypeScript + Vite investigation dashboard
infra/      Dockerfiles, docker-compose.yml, .env.example
docs/       Architecture, database design, API contracts, ML pipeline,
            feature engineering, model evaluation, model card, graph
            analytics, graph scenarios, implementation plan
.github/    CI (GitHub Actions)
```

## Prerequisites

- Docker + Docker Compose v2, **or** Python 3.12 and Node.js 22 for running
  the services directly on your machine.

## Option A: Run everything with Docker Compose

```bash
cp infra/.env.example infra/.env
# edit infra/.env and set real passwords before anything but local/demo use

cd infra
docker compose --env-file .env up --build
```

This starts, in order: `db` (Postgres, with a healthcheck), `migrate` (a
one-off job that runs `alembic upgrade head` as the Postgres admin user,
creating the `app`/`ground_truth` schemas and the `api_service`/`ml_trainer`
roles), `backend` (FastAPI on the host port from `BACKEND_HOST_PORT`, default
`8001`), and `frontend` (Vite dev server on `FRONTEND_HOST_PORT`, default
`5173`).

Once it's up:

- Frontend: http://localhost:5173 — sign in to the investigation workspace.
- Backend health: http://localhost:8001/api/v1/health
- Backend readiness (DB-aware): http://localhost:8001/api/v1/health/ready

Stop and remove containers (keeps the Postgres volume):

```bash
docker compose down
```

> **Note on this project's own development environment:** the sandbox this
> project was built in has very slow registry/network throughput and almost
> no free disk, so the Docker image builds themselves were not completed
> there end-to-end (see "What was and wasn't verified" below). The
> Dockerfiles and compose file are written and reviewed against the
> process-level setup below, which *was* fully verified. Try Option A first;
> if it's slow to pull images on your machine, Option B gives you the same
> result without building containers.

## Option B: Run services directly (what was actually verified during development)

**1. Start Postgres** (any Postgres 16, e.g. via Docker):

```bash
docker run -d --name sentinelai-db \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=sentinelai \
  -p 5432:5432 postgres:16
```

**2. Backend:**

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

export ALEMBIC_DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/sentinelai"
export API_SERVICE_DB_PASSWORD="dev_api_service_password"
export ML_TRAINER_DB_PASSWORD="dev_ml_trainer_password"
alembic upgrade head

export DATABASE_URL="postgresql+psycopg2://api_service:dev_api_service_password@localhost:5432/sentinelai"
uvicorn app.main:app --reload --port 8001
```

**3. Frontend** (in a second terminal):

```bash
cd frontend
npm install
VITE_API_BASE_URL="http://localhost:8001/api/v1" npm run dev
```

Open http://localhost:5173 and sign in with an existing user. System status
checks backend/database connectivity. Ensure `CORS_ORIGINS` matches the exact
frontend origin if Vite chooses a different port.

## Running tests

**Backend** (unit tests run without a database; the integration test needs one
and otherwise reports itself skipped, never a false pass):

```bash
cd backend && source .venv/bin/activate
pytest -v                      # unit tests only, no DB needed
DATABASE_URL="postgresql+psycopg2://api_service:dev_api_service_password@localhost:5432/sentinelai" pytest -v   # includes the live-DB integration tests
ruff check .
```

The graph-analytics tests (`tests/test_graph_*.py`) follow the same split:
`tests/test_graph_metrics.py` and `tests/test_graph_synthetic.py` run
against hand-built/synthetic graphs and need no database;
`tests/test_graph_build.py`, `tests/test_graph_fund_flow.py`,
`tests/test_graph_api.py`, and the one DB-backed case in
`tests/test_graph_performance.py` need the same live Postgres as above and
skip cleanly (not a false pass) without it.

**Frontend:**

```bash
cd frontend
npm run lint
npm run test
npm run build
```

## ML: training a model and scoring a transaction

`ml/` and `backend/` share one virtualenv (`backend/.venv`) in this
project's development setup — see `docs/ml-pipeline.md` §5 for why.

**Install the ML dependencies** (already included in
`backend/requirements.txt`, so this is covered by the Option B backend
setup above):

```bash
cd backend && source .venv/bin/activate
pip install -r requirements.txt   # pandas, scikit-learn, xgboost, shap, matplotlib, joblib
```

**Train a model** (from the repo root):

```bash
# Real PaySim, once you've placed the CSV at ml/data/paysim.csv
# (see docs/ml-pipeline.md §3 for where to get it — not included here).
# This is what actually produced docs/model-evaluation.md's numbers:
# 6.36M rows, ~172s end-to-end on 16 cores / 31GB RAM.
PYTHONPATH=backend backend/.venv/bin/python -m ml.training.train --csv ml/data/paysim.csv

# Synthetic fixture (fast; no download needed; useful for iterating on the
# pipeline itself rather than measuring real performance):
PYTHONPATH=backend backend/.venv/bin/python -m ml.training.train --synthetic
```

This writes a versioned artifact to `ml/artifacts/<version_label>/` and
updates `ml/artifacts/active_version.txt` — which is what the backend
reads to decide what to serve. Reproduce the full evaluation report with
`cat ml/artifacts/$(cat ml/artifacts/active_version.txt)/metadata.json`.

**Score a transaction** (once the backend is running — Option B's step 2 —
and a model has been trained). **Since Phase 6 Part A, this needs the
`service` credential** (`SERVICE_API_KEY` from `infra/.env` —
`docs/authentication.md`):

```bash
curl -s -X POST http://localhost:8001/api/v1/risk/score \
  -H "Authorization: Bearer $SERVICE_API_KEY" -H 'Content-Type: application/json' \
  -d '{
    "transaction_id": "TX-001",
    "transaction_type": "TRANSFER",
    "amount": 8400,
    "sender_id": "ACC-001",
    "receiver_id": "ACC-002",
    "step": 120,
    "oldbalanceOrg": 10000,
    "oldbalanceDest": 500,
    "include_explanation": true
  }' | python3 -m json.tool
```

`sender_id`/`receiver_id` not yet seen in `app.accounts` are scored with
the documented new-account defaults (`docs/feature-engineering.md` §3) —
no fabricated history. See `docs/api-contracts.md` §4.1 for the full
contract, `docs/model-card.md` for what the SHAP numbers in the response
actually mean, and `docs/model-evaluation.md` for the metrics behind the
`threshold`/`risk_level` in the response.

**Replay PaySim into the running backend** (populates `app.accounts`/
`app.transactions` so later `/risk/score` calls see real history).
**Since Phase 6 Part A, this also needs `SERVICE_API_KEY`**:

```bash
SERVICE_API_KEY=<value from infra/.env> PYTHONPATH=backend backend/.venv/bin/python -m ml.data.replay --synthetic --base-url http://localhost:8001/api/v1
```

**ML test suite** (44 tests, no DB needed):

```bash
cd ml && ../backend/.venv/bin/python -m pytest -v
```

## Graph analytics

Once the backend is running and some transactions are ingested (e.g. via
the replay command above), explore an account's transaction network.
**Since Phase 6 Part A, this needs an analyst token** — see
`docs/authentication.md` for creating a user/logging in; `$TOKEN` below
is the `access_token` from that login response.

```bash
# Replace ACCOUNT_ID with a real id from `curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/v1/accounts`
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8001/api/v1/graph/accounts/ACCOUNT_ID?hops=2" | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8001/api/v1/graph/accounts/ACCOUNT_ID/metrics" | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8001/api/v1/graph/accounts/ACCOUNT_ID/transactions" | python3 -m json.tool
curl -s -H "Authorization: Bearer $TOKEN" "http://localhost:8001/api/v1/graph/accounts/ACCOUNT_ID/fund-flow?max_hops=3" | python3 -m json.tool
```

See `docs/graph-analytics.md` for what each endpoint computes and its
bounded-query caps, and `docs/graph-scenarios.md` for the deterministic
synthetic fraud-network fixtures (`backend/app/graph/synthetic.py`) used to
test the structural-pattern algorithms, since real PaySim data has almost
no repeated-sender structure to exercise them against.

## Alerts, cases, and evidence (Phase 5)

First create a user (see `docs/authentication.md` — there is no default
account):

```bash
cd backend
python scripts/create_user.py --email admin@sentinelai.local --role admin --password 'choose-your-own'

TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email": "admin@sentinelai.local", "password": "choose-your-own"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
```

Scoring a transaction and persisting the result (this one call needs
`SERVICE_API_KEY`, not a user token — see `docs/authentication.md`):

```bash
curl -s -X POST http://localhost:8001/api/v1/risk-scores \
  -H "Authorization: Bearer $SERVICE_API_KEY" -H 'Content-Type: application/json' \
  -d '{"transaction_id": "<a real transaction id>", "include_explanation": true}'
```

Listing alerts, creating a case, and attaching evidence:

```bash
curl -s http://localhost:8001/api/v1/alerts -H "Authorization: Bearer $TOKEN"
curl -s -X POST http://localhost:8001/api/v1/cases \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"alert_ids": ["<alert id from above>"], "priority": "high"}'
curl -s -X POST http://localhost:8001/api/v1/cases/<case id>/evidence \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"evidence_type": "analyst_note", "body": "Balance-draining pattern observed."}'
```

See `docs/alerts-and-cases.md` for the full endpoint list, the case
status machine, every evidence type, and the audit log.

## Investigations (Phase 6 — LangGraph multi-agent)

Continuing from the case created above (`$TOKEN` is still an analyst's
token):

```bash
started=$(curl -s -X POST "http://localhost:8001/api/v1/cases/<case id>/investigations" \
  -H "Authorization: Bearer $TOKEN")
run_id=$(echo "$started" | python3 -c "import sys,json; print(json.load(sys.stdin)['run_id'])")
echo "$started"   # {"run_id": "...", "status": "running"}

# Poll until status is "awaiting_approval" (or "failed") — this runs in
# the background, typically well under a second with the mock LLM:
curl -s "http://localhost:8001/api/v1/investigations/$run_id" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# Approve the draft as the case's investigation record (NOT a case
# decision — the case itself is still only resolved via
# POST /cases/{id}/decision, senior_analyst/admin only):
curl -s -X POST "http://localhost:8001/api/v1/investigations/$run_id/approve" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

See `docs/investigation-workflow.md` for the full walkthrough (including
the exact step/evidence-reference shape), `docs/multi-agent-architecture.md`
for how the three agents and the LangGraph workflow are built,
`docs/agent-tools.md` for what each agent can retrieve, and
`docs/agent-security.md` for the full security posture. **The LLM is a
deterministic mock in this environment** — see `docs/agent-security.md`
§1.

## Environment variables

See `infra/.env.example` for the full, commented list used by Docker Compose.
Running services directly uses the same variable names (`DATABASE_URL`,
`ALEMBIC_DATABASE_URL`, `API_SERVICE_DB_PASSWORD`, `ML_TRAINER_DB_PASSWORD`,
`JWT_SECRET_KEY`, `SERVICE_API_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`,
`VITE_API_BASE_URL`, etc.) — see the commands above.

Phase 6 adds `LLM_PROVIDER` (`mock` by default — the only value this
environment can actually run, since no key below is configured),
`LLM_MODEL_NAME`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and
`AGENT_NODE_TIMEOUT_SECONDS` — see `docs/agent-security.md` §1.

## What was and wasn't verified

Done and actually run, not assumed:

- Backend test suite (167 tests, through Phase 6) and ML test suite (44
  tests) both pass — against a real Postgres 16 instance for every
  backend test that needs one, never faked or skipped-and-reported-as-
  passing. `ruff check .` and `mypy app`/`mypy data training explain`
  pass for backend and ml respectively.
- Migrations `0001`–`0003` applied cleanly to a real database (schemas,
  roles, grants, then `app.accounts`/`app.transactions`, then the isolated
  `ground_truth.transaction_labels`).
- Ground-truth isolation re-verified against the live database after adding
  real tables to both schemas (`backend/tests/test_security_isolation.py`,
  plus a manual `psql` check during development): `api_service` gets
  "permission denied for schema ground_truth" on a `SELECT`; `ml_trainer`
  gets "permission denied for table accounts" on an `INSERT`; `ml_trainer`
  really can `SELECT` from `ground_truth`.
- `ml.training.train` ran end-to-end against the **real PaySim dataset**
  (6,362,620 rows, user-supplied), producing a real artifact with real
  metrics — see `docs/model-evaluation.md` (test F1 0.887, ROC-AUC 0.999,
  SHAP additivity error ~8×10⁻⁸). A real scalability bug was found and
  fixed in the process: the first version of the historical-feature
  computation iterated per sender in Python, which was fine against test
  fixtures but — against real PaySim's actual structure of ~6.35M
  near-singleton sender groups — consumed 28 of 31GB RAM and was still
  running after 27 minutes before being killed. Rewritten to use only
  vectorized pandas groupby/merge_asof operations; re-verified against the
  same hand-constructed test case, then measured at 91.2s / 6.4GB peak RSS
  on the full real dataset. See `docs/ml-pipeline.md` §6 for the full
  account, including a 7-point leakage audit (no leakage found) run before
  training on real data.
- `POST /transactions/ingest`, the account/transaction list/detail
  endpoints, and `POST /risk/score` (including `include_explanation: true`)
  were exercised through FastAPI's `TestClient` against the real local
  Postgres — real rows inserted, real history computed, real model
  loaded and scored, real SHAP contributions returned and checked for
  internal consistency (sorted by magnitude, valid directions).
- `backend/tests/test_feature_consistency.py` cross-checks the SQL-based
  (inference) and bulk-pandas (training) historical-feature computations
  against the same hand-seeded scenario and confirms they agree exactly.
- A real pre-existing bug was found and fixed this way: the Phase-1
  validation-error handler serialized `exc.errors()` directly, which broke
  as soon as a `Decimal`-typed field (introduced by this phase's
  `amount`/balance fields) failed validation — `TypeError: Object of type
  Decimal is not JSON serializable`. Fixed with `fastapi.encoders.
  jsonable_encoder` (`backend/app/main.py`).
- Frontend lint, tests, and production build all pass (unchanged from
  Phase 1 — this phase didn't touch the frontend).
- **Graph analytics (Phase 4)**: all 48 tests, including the 20 DB-backed
  neighborhood/fund-flow/API-integration tests and the one DB-backed
  performance test, were run and verified to pass against the real local
  Postgres — resolving the earlier limitation recorded here (and in
  `docs/graph-analytics.md` §7) that those 20 could only be verified to
  skip cleanly, not actually execute, because the `api_service` role
  password in `infra/.env` wasn't yet reconciled with a working local
  `DATABASE_URL`. That reconciliation (reading the already-running
  `infra-db-1` container's real credentials and exporting them for a
  local `pytest` run, without printing them) is exactly what made the
  rest of this verification — Phase 5's 124 tests — possible too.
- **Phase 5 (alerts, cases, evidence, audit, auth)**: all of the above,
  plus 45 new tests (auth, risk-score persistence/idempotency/dedup,
  alerts, cases, case decisions and status transitions, evidence
  resolution/rejection, audit logging) were run against the same real
  Postgres instance and pass — see `docs/alerts-and-cases.md` and
  `docs/authentication.md` for the full design and known limitations.
  Migration `0004` (8 new tables) applied cleanly.
- **Phase 6 (LangGraph multi-agent investigations)**: 34 new tests
  (tool-permission boundaries, LLM provider selection/fallback-refusal,
  report evidence-reference validation, ground-truth isolation of the
  agent tools, prompt-injection-shaped input, human-approval enforcement,
  the full start→evidence→network→report→approve lifecycle, idempotent
  approve/reject, bounded request-revision) run against the same real
  Postgres instance and pass. Migration `0005` (3 new tables) applied
  cleanly. **Part A also closed the Phase 1–4 authentication gap**: every
  pre-existing route (`/transactions/ingest`, `/risk/score`, `/graph/*`,
  `/accounts`, `/transactions`) was given the appropriate `service`/
  `analyst+` requirement, and every existing test for those routes
  (`test_ingestion.py`, `test_risk_score_api.py`, `test_graph_api.py`,
  `test_graph_build.py`, `test_graph_fund_flow.py`,
  `test_graph_performance.py`, `test_accounts_transactions_api.py`) was
  updated to authenticate rather than left broken, plus new tests for the
  rejection paths. A real bug was found and fixed in the process:
  `ml/data/replay.py` called the now-protected `/transactions/ingest`
  with no credential at all — fixed to require `SERVICE_API_KEY`
  (`--service-api-key` or the environment variable), never hardcoded.
  A second real bug, inside the new agent code itself, was found by
  actually running the pipeline end-to-end against a real database
  rather than only against mocks: `get_account_profile` was called with
  an off-by-one `as_of_step` that let a transaction count as its own
  prior history — see `docs/multi-agent-architecture.md` §4 for the fix.
  **The LLM is a deterministic mock in this environment** (§1 of
  `docs/agent-security.md`) — no real-provider inference was performed
  or claimed.

Not verified, and not claimed as working: a full `docker compose up --build`
of this exact `infra/docker-compose.yml` with the current backend image.
This was already a known limitation in this same sandbox during Phase 1
(slow/intermittent registry throughput inside the Docker build network),
and it recurred here: `pip install` inside the `backend`/`migrate`
image build timed out downloading the large ML wheels this phase adds
(xgboost, scipy, scikit-learn) three times in a row, even after raising
`pip`'s timeout/retry limits (`infra/backend.Dockerfile`). The process-level
setup (Option B) *was* fully verified end-to-end, including against the
same containerized Postgres `docker compose` already has running — only the
backend/migrate *image rebuild* itself is unverified. If your network is
faster than this sandbox's, `docker compose up --build` should work; if it
times out, retrying the single `pip install` step (or pre-pulling the wheels
some other way) is the fix, not anything in the application code.

## Known limitations / incomplete functionality

- ~~Authentication only covers the Phase 5 surface~~ — **closed in
  Phase 6 Part A**; see `docs/authentication.md`'s "Known limitations"
  for exactly what changed.
- **No refresh tokens or logout** — see `docs/authentication.md`.
- **The investigation LLM is a deterministic mock** in this
  environment — no API key is configured. The real-provider code path
  (`AnthropicLLMProvider`/`OpenAILLMProvider`, `app/agents/llm.py`) is
  implemented but unverified against a real endpoint. See
  `docs/agent-security.md` §1 and §9.
- **No automatic resume of an in-flight investigation after a backend
  restart** — a run's history up to the restart is never lost, but
  nothing re-schedules it; see `docs/multi-agent-architecture.md` §2.5
  and §5. There's no message queue in the approved stack to build true
  crash-recovery on without adding infrastructure this project doesn't
  otherwise use.
- **Investigation node timeouts are cooperative, not preemptive** — a
  hung node is abandoned by the caller after the timeout, not killed;
  see `docs/multi-agent-architecture.md` §2.3 for why (a real LangGraph
  version constraint, found while building this phase).
- **No graph-structural-rule-triggered alerts, no conditional branching
  in the investigation graph** — see `docs/alerts-and-cases.md` §7 and
  `docs/multi-agent-architecture.md` §5 respectively.
- **No alert creation from graph-structural rules** — only
  `POST /risk-scores`'s model-threshold path creates alerts today;
  `alert_type`'s schema already allows `"graph_structural"`/`"manual"`
  values for when that's added. See `docs/alerts-and-cases.md` §7.
- **No `ml-train` Compose service** — training runs via a local script
  against the shared venv, not a containerized job; see
  `docs/ml-pipeline.md` §6 for the disk-cost rationale for not adding one
  yet. The backend container *does* mount `ml/artifacts/` read-only so it
  can serve whatever that script produces.
- Fan-in/fan-out thresholds (graph analytics) are a fixed heuristic
  rather than tuned, and cycle detection is bounded to 6-node cycles by
  default.
- The Phase 7 UI is implemented. Its automated and browser fixture checks are
  documented in `docs/frontend-qa.md`; live authenticated backend workflows
  still need verification. Some requested analytics/search/history require
  API endpoints that do not currently exist.
- The frontend Docker image runs the Vite **dev** server, not a production
  static build behind nginx — deferred to the deployment-polish phase.
