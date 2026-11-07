# SentinelAI — Implementation Plan

## Current Status

**Phases 1–6 complete.** Verified, not assumed:

- Phase 1: FastAPI skeleton, `/health`/`/health/ready`, Alembic baseline
  migration (schemas + `api_service`/`ml_trainer` roles + ground-truth grants),
  CI (lint, type-check, pytest for backend; lint/test/build for frontend).
  `docker compose up` brings up `db`+`migrate`+`backend`+`frontend`.
- Phase 2 (data model + ingestion): `app.accounts`/`app.transactions` tables
  and SQLAlchemy models (migration `0002`); `ground_truth.transaction_labels`
  (migration `0003`, no ORM model in `backend/app` by design); `POST
  /transactions/ingest` + `GET /accounts`, `/accounts/{id}`, `/transactions`,
  `/transactions/{id}`; a PaySim replay script (`ml/data/replay.py`) and an
  admin-credentialed ground-truth loader (`ml/data/load_ground_truth.py`). A
  live-DB test confirms `api_service` cannot `SELECT` from `ground_truth` and
  `ml_trainer` cannot write `app` tables (`backend/tests/test_security_isolation.py`).
- Phase 3 (ML training + inference), **except `risk_scores`/`alerts`
  persistence and `/scoring/batch-score`/`/models/active`, deferred**: chronological
  split with an integrity test; leakage-free shared feature engineering
  (`backend/app/ml/features.py`, imported by both training and inference);
  dummy/logistic-regression/XGBoost trained and compared; threshold tuned on
  validation only, evaluated once on test; SHAP wired to XGBoost with a
  verified additivity check; `POST /risk/score` (documented in
  `docs/api-contracts.md` §4.1, a new endpoint added for this phase) scoring
  through the real backend against a real trained artifact. **Trained and
  evaluated on the real PaySim dataset** (6,362,620 rows, user-supplied) —
  see `docs/model-evaluation.md` for real measured metrics (test F1 0.887,
  ROC-AUC 0.999). A real scalability bug was found and fixed validating
  against the real data's actual structure (6.35M near-singleton sender
  groups broke the original per-group implementation); see
  `docs/ml-pipeline.md` §6 for that and a 7-point leakage audit (no leakage
  found) run before training on real data.
- Phase 4 (graph analytics): bounded k-hop NetworkX neighborhood construction
  (`backend/app/graph/build.py`), structural-pattern algorithms (fan-in/out,
  unique counterparties, velocity, connected components, cycle detection —
  `backend/app/graph/metrics.py`), time-aware forward-in-time fund-flow
  tracing (`backend/app/graph/fund_flow.py`), four deterministic synthetic
  fraud-network scenarios (`backend/app/graph/synthetic.py`), and four new
  `/graph/accounts/{id}` endpoints (`docs/api-contracts.md` §2.1). 48 tests,
  **all since verified to actually pass against a real local database**
  (the earlier limitation recorded here — that the 20 DB-backed tests
  could only be confirmed to skip cleanly, not run — was resolved in a
  later verification pass that reconciled the local `DATABASE_URL` with
  the running Postgres container's real `api_service` credentials; see
  `docs/graph-analytics.md` §7 for the original account and README.md
  for the resolution). `docs/graph-scenarios.md` has the synthetic-
  scenario rationale.
- **Phase 5 (alerts, cases, evidence, audit, auth) complete**, verified
  against a real PostgreSQL database: `risk_scores` persistence
  (`POST /risk-scores`, idempotent, deduplicated alerting —
  `backend/app/services/scoring_persistence.py`), alert
  listing/detail/status-transition (`backend/app/api/routes/alerts.py`),
  case creation/assignment/status-machine/decision
  (`backend/app/api/routes/cases.py`, `backend/app/services/cases.py`),
  server-resolved case evidence (`backend/app/services/evidence.py`,
  8 types), append-only audit logging
  (`backend/app/services/audit.py`), and a minimal real JWT+bcrypt auth
  system (`backend/app/core/security.py`, `backend/app/api/deps.py`) —
  see `docs/alerts-and-cases.md` and `docs/authentication.md` for full
  design and deviations from the original design-time sketch. Migration
  `0004` adds 8 tables.
- **Phase 6 (LangGraph multi-agent investigations) complete** — see the
  Phase 6 section below and `docs/multi-agent-architecture.md`,
  `docs/agent-tools.md`, `docs/agent-security.md`,
  `docs/investigation-workflow.md`. This phase's Part A also closed
  Phase 5's auth-scope limitation: ingestion, scoring, graph, and plain
  accounts/transactions routes now require the same `service`/`analyst+`
  principals as everything else (`docs/authentication.md`).
  Migration `0005` adds 3 more tables (`agent_runs`, `agent_steps`,
  `agent_evidence_refs`).
- **167 backend tests pass (0 failed, 0 skipped)** as of Phase 6,
  against a real PostgreSQL database throughout; `ruff check .` and
  `mypy app` both pass. The LLM backing every verified investigation run
  is an explicitly-labeled deterministic mock — no LLM API key is
  configured in this environment (`docs/agent-security.md` §1).
- **Phase 7 frontend implemented**: see `frontend-architecture.md`, `design-system.md`,
  `ux-flows.md`, and `dashboard-user-guide.md`. Automated and browser fixture
  verification is recorded in `frontend-qa.md`. Live backend end-to-end verification
  remains pending; the original backend test counts above are historical Phase 6 results.

**Note on phase ordering**: this plan's own Phase 2 (data model) and Phase 3
(ML) were built together, out of the plan's original phase numbering, on
explicit direction given when the ML work was requested — the data model
("just enough of Phase 2") was added first specifically because the ML
phase's inference endpoint needed a real historical-data source to query,
per this plan's own "don't skip dependencies" rule. Phase 2's full scope
(a complete replay-based ingestion demo, already-ingested sample data) was
not separately pursued beyond what Phase 3 needed.

This plan is sequential by dependency: each phase assumes the previous phase's
artifacts exist. It is not a time estimate.

## Phase 1 — Repository & Infrastructure Scaffolding

**Owner skills**: `devops-engineer`, `system-architect`

- Create the monorepo layout from `CLAUDE.md` (`backend/`, `ml/`, `frontend/`,
  `infra/`, `.github/workflows/`).
- `infra/docker-compose.yml`: `postgres`, `backend`, `frontend`, `ml-train`
  (job-style, not long-running), per `docs/architecture.md` §8.
- `infra/.env.example` listing every required variable (DB URL per role, JWT
  secret, model artifact path) with placeholder values only.
- FastAPI skeleton: app factory, `/health`, `/health/ready`, config loading.
- Alembic initialized, baseline migration creating the `app` and `ground_truth`
  schemas and the role grants from `docs/database-design.md` §3.
- `.github/workflows/ci.yml`: lint (ruff, eslint), type-check (mypy or pyright,
  tsc), `pytest` (empty suite passes trivially at this point).

**Exit criteria**: `docker compose up` brings up Postgres + an empty FastAPI app
responding on `/health`; CI runs and is green on an empty test suite; migration
applies cleanly to a fresh database.

## Phase 2 — Data Model & Synthetic Ingestion

**Owner skills**: `backend-engineer`, `ml-engineer`

- SQLAlchemy models for every `app` table in `docs/database-design.md` §2;
  corresponding Alembic migration.
- PaySim loader in `ml/data/`: validates the raw CSV, writes `ground_truth`
  labels only via the `ml_trainer` role.
- Replay/ingestion path: a script or `service`-role job that reads PaySim rows in
  `step` order and calls `POST /transactions/ingest` (§3 of
  `docs/api-contracts.md`), simulating chronological arrival.
- Backend read endpoints for accounts/transactions (no scoring yet).

**Exit criteria**: a full PaySim sample loads into `app.transactions`/`accounts`;
`ground_truth.transaction_labels` is populated separately; a direct query proves
the `api_service` role cannot `SELECT` from `ground_truth` (automated test, not
a manual check, per `security-reviewer`'s rules).

## Phase 3 — ML Training Pipeline & Inference Integration

**Owner skill**: `ml-engineer`

- Chronological split (train/validation/test by `step`, no shuffling across
  boundaries); an automated test that fails if any row crosses its boundary.
- Feature engineering restricted to pre-event, pre-transaction data; an
  automated leakage test asserting `isFraud`/`isFlaggedFraud` and any
  post-event field are absent from the feature set.
- Baseline model + XGBoost; evaluation on precision, recall, F1, PR-AUC, and
  false-positive rate — computed and recorded, never estimated.
- SHAP explainer wired to the trained model.
- `metadata.json` written alongside the artifact with the training window,
  feature list, and the actual measured metrics.
- Backend `ml` inference module: loads the active artifact, recomputes features
  at request time, returns score + SHAP via `/transactions/{id}/risk-score` and
  `/transactions/{id}/explanation`.
- Model card (owned jointly with `documentation-engineer`) stating real measured
  metrics and known limitations (class imbalance, synthetic-data-only scope).

**Exit criteria**: training runs end-to-end on PaySim, produces a versioned
artifact + metadata; leakage and chronological-integrity tests pass; the backend
can score a transaction through the API and return a SHAP explanation that
matches what the model actually produced.

## Phase 4 — Graph Analytics Engine

**Owner skill**: `graph-analytics`

- `graph` module: build a bounded subgraph from `app.transactions`, compute
  fan-in/out, degree, cycle detection, shortest-path between flagged accounts.
- Synthetic fraud-network generator for test fixtures (deterministic, seeded).
- `GET /accounts/{id}/graph-neighborhood` wired to real data.
- Tests against small, hand-constructed graphs with known expected metrics —
  not just "the code runs."

**Exit criteria**: neighborhood endpoint returns correct nodes/edges/metrics for
both real ingested data and the synthetic fixture graphs; metrics are explicitly
labeled as structural signal, not a fraud determination, anywhere they're
surfaced.

## Phase 5 — Alerts & Case Management — **complete**

**Owner skill**: `backend-engineer`

- Alert creation from score threshold (`POST /risk-scores`) — **done**.
  Graph-rule-triggered alerts are **not implemented**: `alert_type`'s
  `CHECK` constraint allows `"graph_structural"`/`"manual"` values, but
  nothing creates one that way yet (deferred to Phase 6+, once there's an
  agent or scheduled job to run a rule — see `docs/alerts-and-cases.md` §7).
- Case CRUD, case-alert linking — **done**. Case notes were implemented as
  `case_evidence` with `evidence_type="analyst_note"`, not a separate
  `case_notes` table — see `docs/alerts-and-cases.md` §1 for why.
- `/cases/{id}/decision` endpoint enforcing `senior_analyst`/`admin` role and a
  min-10-char rationale; writes `case_decisions` and an `audit_log_entries` row
  — **done**, tested (`backend/tests/test_cases_api.py`).
- Audit logging for auth events and case decisions — **done**, extended to
  every case/alert/evidence mutation (`docs/alerts-and-cases.md` §6).
- Beyond the original scope of this section: a minimal real auth system
  (JWT + bcrypt, `docs/authentication.md`) and structured case evidence
  (`POST /cases/{id}/evidence`, 8 server-resolved types) were added, since
  "resolved only through a role-checked... decision endpoint" requires a
  real role-check mechanism to exist, and §7 of the governing brief asked
  for evidence integration explicitly.

**Exit criteria — met**: an alert is created from `POST /risk-scores`
crossing the active threshold, can be triaged into a case
(`POST /cases`), and resolved only through `POST /cases/{id}/decision`
(role-checked, rationale-required — a `PATCH` to `status: "resolved"` is
rejected regardless of the case's current state); every decision
produces an audit log entry; tests cover the role check, the rationale
requirement, and the `PATCH`-cannot-resolve invariant. All verified
against a real PostgreSQL database — 124 backend tests pass (0 failed,
0 skipped), `ruff check .` and `mypy app` pass.

## Phase 6 — LangGraph Investigation Agents — **complete**

**Owner skill**: `multi-agent-engineer`

- Workflow graph — **done**, with one deliberate simplification from the
  original `docs/architecture.md` §7 sketch: `HypothesisSynthesis` and
  `ReportDraft` are merged into one `report_writer` node (one LLM/mock
  call builds validated hypotheses and drafts the report together,
  rather than two separate agent turns) — see
  `docs/multi-agent-architecture.md` §1 for why. Final graph: `intake →
  evidence_collector → network_investigator → report_writer →
  human_approval_gate`.
- Read-only tools (§6.2 of `docs/api-contracts.md`) — **done**, backed
  by `api_service`, with an explicit per-agent permission allow-list
  (`app/agents/tools.py::AGENT_TOOL_PERMISSIONS`) enforced at every
  call — `docs/agent-tools.md`.
- Structured-output validation — **done**: every hypothesis must cite a
  real, actually-collected evidence reference or is dropped before the
  draft is returned (`app/agents/graph.py::report_writer_node`),
  checked in code, not left to the model.
- Postgres-backed persistence — **done**, as `agent_runs`/`agent_steps`/
  `agent_evidence_refs` (migration `0005`), not via LangGraph's own
  checkpointer — see `docs/multi-agent-architecture.md` §2.4 for why.
- `/cases/{id}/investigations`, `/investigations/{run_id}`,
  `/investigations/{run_id}/approve|request-revision|reject` — **done**,
  `docs/investigation-workflow.md`.
- Tests — **done**: 34 new tests (`tests/test_agent_tool_permissions.py`,
  `test_agent_llm_mock.py`, `test_agent_graph_nodes` logic covered via
  `test_agent_security.py`, `test_investigations_api.py`) assert every
  report claim traces to a real, collected evidence reference, and that
  the workflow halts at `awaiting_approval` rather than auto-finalizing.
- Beyond the original scope of this section: Part A of this phase closed
  the pre-existing Phase 1–4 authentication gap (`docs/authentication.md`),
  and Part G added a configurable LLM provider abstraction defaulting to
  an explicitly-labeled deterministic mock, since no LLM API key is
  configured in this environment (`docs/agent-security.md` §1).

**Exit criteria — met**: a full investigation run on real ingested data
(not a fixture — a real `Case`/`Alert`/`Transaction` through the actual
API) produces a draft report with verifiable evidence citations; the run
cannot reach `approved` without an explicit `/approve` call
(`tests/test_agent_security.py::test_investigation_never_auto_approves`);
167 backend tests pass (0 failed, 0 skipped) including the pre-existing
133; `ruff check .` and `mypy app` pass. **Caveat**: the LLM backing
every verified run is the deterministic mock (§1 of `docs/agent-security.md`)
— the real-provider code path is implemented but has not been executed
against a real model in this environment.

## Phase 7 — Frontend Dashboard

**Owner skill**: `frontend-engineer`

**Implementation status (2026-11-07)**: all frontend modules are connected to typed API
clients; stages A/B were documented before the first slice, and actual Chromium
screenshots of stage C were inspected before stage E. Stage F verification and
remaining live-service limitations are recorded in `frontend-qa.md`.

- Typed API client, separated from UI components.
- Transaction/alert explorer (tables, filters).
- Recharts views: score distributions, alert volume over time, model
  performance (only once Phase 3 metrics exist — never mocked as if live).
- Cytoscape.js network view consuming the implemented `/graph/accounts/{id}` endpoint.
- Case investigation UI: notes, agent run viewer (steps + draft report),
  approve/request-revision/reject actions, decision form.
- Loading/empty/error states on every data view; synthetic/demo data clearly
  labeled wherever shown.

**Exit criteria**: an analyst can, end to end in the UI, view an alert, open a
case, run an investigation, review the draft report with its citations, and
record a decision.

## Phase 8 — Testing Hardening & Security Review

**Owner skills**: `testing-engineer`, `security-reviewer`

- Raise backend/ML/graph/agent coverage on edge cases and failure paths
  (invalid input, missing data, model artifact absent, graph query on
  disconnected node, agent tool failure).
- Frontend component and basic end-to-end tests for the golden path.
- Security pass: auth/role checks on every sensitive route, secrets handling,
  `ground_truth` isolation re-verified against the current schema/grants,
  prompt-injection handling in agent tool outputs, audit log completeness.
- CI gate: coverage reporting, all lint/type-check/test steps required for
  merge.

**Exit criteria**: security checklist signed off with findings documented and
either fixed or explicitly deferred with rationale; CI enforces the full gate.

## Phase 9 — Deployment Polish & Documentation

**Owner skills**: `devops-engineer`, `documentation-engineer`

- Finalize Compose profiles (dev vs. demo), health checks, startup ordering.
- README: real setup instructions, matching actual commands.
- Architecture/API/database docs updated to match whatever changed during
  implementation (these are living documents, not fixed at design time).
- Model card finalized with real metrics.
- Demo script: a scripted walkthrough using only synthetic data.

**Exit criteria**: a fresh clone can `docker compose up`, load sample data, and
walk the full demo path using only the README.

## Dependencies Summary

Phase 2 depends on Phase 1 (DB + roles exist). Phase 3 depends on Phase 2 (real
ingested + labeled data to train on). Phase 4 depends on Phase 2 (transactions
to build graphs from) and can proceed in parallel with Phase 3. Phase 5 depends
on Phase 3 and 4 (needs scores and graph signal to generate alerts). Phase 6
depends on Phase 5 (needs cases to investigate) and Phase 4 (graph tool). Phase 7
depends on Phases 3–6 (needs real endpoints to visualize, not mocks). Phase 8
and 9 depend on everything before them.

## Risks / Watch Items

- **Class imbalance** in PaySim (fraud is a small minority of transactions) may
  make precision/recall tradeoffs harsh; Phase 3 must report this honestly
  rather than cherry-picking a threshold that looks good.
- **LangGraph checkpointer choice** (Phase 6) affects how durable
  in-progress runs are across restarts — flagged as an open decision below.
- **Frontend/demo scope creep**: Phase 7 should visualize only what Phases 3–6
  actually produce; it must not invent chart data to fill out the dashboard
  before the backing endpoint exists.

## Phase 7.5 — demo and unified workflow

- Added owned, deterministic, atomic demo batches (migration 0006), explicit demonstration alert types (0007), and probability precision (0008).
- Reused production feature/history definitions, actual frozen XGBoost inference and probability-space SHAP. No training or ground-truth imports.
- Added enriched JWT-protected workspace read models, serialized case/report entry points, and database-backed scenario cards.
- Reduced primary navigation to Dashboard, Alerts, Investigations and Transactions. Contextual history, graph, evidence, report progress/review and human case decisions share one workspace.
- Added PostgreSQL generator/ML/reset/concurrency/RBAC regression tests and a browser check against the real API. See frontend-qa.md for final measured results and known limitations.
- Existing case/report APIs remain available; automatic entry points reuse existing work. Reset refuses external references and active reports, and retains audit history.
