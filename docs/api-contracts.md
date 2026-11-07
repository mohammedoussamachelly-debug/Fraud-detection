# SentinelAI — API Contracts

Status: **implemented through Phase 6**, plus three small read-only
additions from Phase 7 (§6: `GET /cases/{id}/evidence`,
`GET /cases/{id}/investigations`, `GET /cases/{id}/decision` — the
case-detail/investigation UI needs to list/re-display what's already
been attached/run/decided, which nothing before Phase 7 exposed), with
the specific exceptions noted inline
(`/scoring/batch-score`, `/models/active`, `/auth/refresh`,
`/auth/logout` — see §1 and §4). This is the interface every
`backend-engineer` route must match — per `system-architect`'s rule, the contract
exists before the handler.

Base path: `/api/v1`. All responses are JSON. All list endpoints are paginated
with `limit`/`offset` (`limit` default 25, max 100) and return `{items, total,
limit, offset}`.

## 0. Conventions

**Auth**: Bearer JWT in `Authorization: Bearer <token>`, issued by `/auth/login`.
Roles: `analyst`, `senior_analyst`, `admin`. A fourth principal, `service`, is
used only by the PaySim replay/ingestion job and the ML artifact-reload trigger —
it is a machine credential, not a human role, and has no case-decision rights.

**Errors**: `application/problem+json` (RFC 7807-style):

```json
{
  "type": "https://sentinelai.dev/errors/validation-error",
  "title": "Validation error",
  "status": 422,
  "detail": "amount must be >= 0",
  "instance": "/api/v1/transactions/ingest"
}
```

**No endpoint in this document returns a ground-truth fraud label.** That is
intentional and absolute — see `docs/database-design.md` §3. If a future change
proposes such an endpoint, it must first update `CLAUDE.md`'s security rules and
get `security-reviewer` sign-off; this document should not be edited to add one
without that.

## 1. Auth

**Implemented in Phase 5** (`docs/authentication.md`), with one
deviation from this original sketch: **no refresh token and no logout
endpoint** — a session is a stateless JWT valid until it expires
(`ACCESS_TOKEN_EXPIRE_MINUTES`, default 30) or the user is deactivated.
See `docs/authentication.md`'s "Known limitations" for why.

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/auth/login` | any | `{email, password}` → `{access_token, token_type: "bearer", expires_in}` |
| GET | `/auth/me` | authenticated | the current user (`{id, email, role, is_active}`) |

## 2. Accounts

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/accounts` | analyst+ | list, filter by `external_ref`, `account_type` |
| GET | `/accounts/{id}` | analyst+ | account detail + transaction count summary |
| GET | `/accounts/{id}/graph-neighborhood` | analyst+ | k-hop subgraph (query params `hops` default 2, max 4; `as_of_step` optional) → nodes/edges for Cytoscape.js |

Response shape, `GET /accounts/{id}/graph-neighborhood`:

```json
{
  "center_account_id": "uuid",
  "nodes": [{"id": "uuid", "external_ref": "C123...", "account_type": "customer"}],
  "edges": [{"source": "uuid", "target": "uuid", "transaction_id": "uuid", "amount": 1500.00, "step": 42}],
  "metrics": {"fan_in": 3, "fan_out": 7, "degree": 10}
}
```

### 2.1 Graph analytics

Added in the graph-analytics phase (`docs/implementation-plan.md` Phase 4),
implemented in `backend/app/api/routes/graph.py`; see `docs/graph-analytics.md`
for the full design and the underlying algorithms. These are a more
detailed alternative to §2's `/accounts/{id}/graph-neighborhood` sketch —
that endpoint was never implemented; these four were, under a dedicated
`/graph` prefix so graph-specific query params (`hops`, `as_of_step`,
`max_hops`, `max_branches`) don't collide with the plain accounts routes.
Every response below includes a `disclaimer` field (the same string on
every endpoint) stating that these are structural signals, not a fraud
determination — per `CLAUDE.md`'s rule against agents/APIs asserting a
fraud conclusion.

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/graph/accounts/{account_id}` | analyst+ | Bounded k-hop neighborhood: nodes, edges, detected cycles. Query params: `hops` (int, 1–4, default 2), `as_of_step` (int ≥ 0, optional). |
| GET | `/graph/accounts/{account_id}/metrics` | analyst+ | Structural metrics for one account (fan-in/out, unique counterparties, velocity). Query params: `as_of_step` (optional). |
| GET | `/graph/accounts/{account_id}/transactions` | analyst+ | The account's own transactions, each labeled `direction: "incoming"\|"outgoing"`, paginated. Query params: `as_of_step`, `limit` (default 25, max 100), `offset`. |
| GET | `/graph/accounts/{account_id}/fund-flow` | analyst+ | Time-aware onward-transfer paths from the account (`step` strictly increasing along each path). Query params: `as_of_step`, `max_hops` (1–5, default 3), `max_branches` (1–10, default 3). |

All four: `404` if `account_id` doesn't exist; `422` for an out-of-range
query parameter. None reads or exposes `ground_truth` data (§6 of
`docs/database-design.md`); all run under the `api_service` role, same as
every other route in this backend.

Response shape, `GET /graph/accounts/{account_id}`:

```json
{
  "center_account_id": "uuid",
  "hops": 2,
  "as_of_step": null,
  "nodes": [{"id": "uuid", "external_ref": "C123...", "account_type": "customer"}],
  "edges": [{"source": "uuid", "target": "uuid", "transaction_id": "uuid", "external_ref": "TX-001", "amount": 1500.00, "step": 42, "type": "TRANSFER"}],
  "cycles": [["C123...", "C456...", "C789..."]],
  "truncated": false,
  "disclaimer": "Structural signal derived from transaction connectivity only. ..."
}
```

Response shape, `GET /graph/accounts/{account_id}/metrics`:

```json
{
  "account_id": "uuid",
  "as_of_step": null,
  "incoming_transaction_count": 6,
  "outgoing_transaction_count": 0,
  "unique_senders": 6,
  "unique_recipients": 0,
  "fan_in_pattern": true,
  "fan_out_pattern": false,
  "velocity_window_steps": 24,
  "velocity_count": 2,
  "truncated": false,
  "disclaimer": "Structural signal derived from transaction connectivity only. ..."
}
```

Response shape, `GET /graph/accounts/{account_id}/fund-flow`:

```json
{
  "source_account_id": "uuid",
  "as_of_step": null,
  "max_hops": 3,
  "max_branches": 3,
  "paths": [
    {"steps": [{"transaction_id": "uuid", "transaction_external_ref": "TX-001", "from_account_id": "uuid", "to_account_id": "uuid", "amount": 8400.00, "step": 120}]}
  ],
  "truncated": false,
  "disclaimer": "Structural signal derived from transaction connectivity only. ..."
}
```

See `docs/graph-analytics.md` §6–7 for the bounded-query caps behind
`truncated` and this phase's known limitations (most notably: these
endpoints were implemented and unit/synthetic-tested, but the live-database
integration tests could not be executed in this phase's development
environment — see that document for why).

## 3. Transactions

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/transactions` | analyst+ | list, filter by `account_id`, `type`, `step` range, `amount` range |
| GET | `/transactions/{id}` | analyst+ | transaction detail |
| GET | `/transactions/{id}/risk-score` | analyst+ | latest `risk_scores` row for this transaction |
| GET | `/transactions/{id}/explanation` | analyst+ | SHAP explanation for the latest score: `{feature, value, shap_contribution}[]` |
| POST | `/transactions/ingest` | service | batch ingest `{transactions: [...]}` from the PaySim replay; writes `app.transactions`/`app.accounts` only — never `ground_truth` |

## 4. Scoring (internal/service)

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/scoring/batch-score` | service | score a *batch* of newly ingested transaction ids in one call — **not implemented**; `POST /risk-scores` (§4.2, Phase 5) does the same persistence/alerting one transaction at a time |
| GET | `/models/active` | analyst+ | currently active model artifact's version label/training window/metadata URI — **not implemented**; there is no `model_versions` table (see `docs/alerts-and-cases.md` §1) to back it |

### 4.1 Synchronous risk scoring — `POST /risk/score`

Added in the ML phase (`docs/implementation-plan.md` Phase 3) ahead of
`risk_scores` DB persistence and `/scoring/batch-score`/`/models/active`
above: this is a **stateless** scoring call — it reads sender history from
`app.transactions` (strictly `step <` the request's `step`) to compute the
historical features, scores the transaction through the active model
artifact, and returns the result directly. It does not require the
transaction to have been ingested first, and does not write anything —
intentionally, since `risk_scores`/`alerts` tables and
`/scoring/batch-score`'s batch, persisted flow are out of scope here (see
"Limitations" in `docs/model-evaluation.md`).

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/risk/score` | service | score one transaction; optionally include its SHAP explanation |

Request:

```json
{
  "transaction_id": "TX-001",
  "transaction_type": "TRANSFER",
  "amount": 8400,
  "sender_id": "ACC-001",
  "receiver_id": "ACC-002",
  "step": 120,
  "oldbalanceOrg": 10000,
  "oldbalanceDest": 500,
  "include_explanation": true
}
```

`sender_id`/`receiver_id` are account `external_ref` values. `oldbalanceOrg`/
`oldbalanceDest` are the sender's/receiver's balances *immediately before*
this transaction — required fields, provided by the caller, never looked up
from a later/other state (there is no "current balance" column on
`accounts`, by design). `num_prev_txns_by_sender` and the other historical
aggregates are *not* request fields — they are derived server-side from
`app.transactions` as of (strictly before) `step`, per
`app/services/history.py`. An account never seen before gets the documented
new-account defaults (`docs/feature-engineering.md`), not a fabricated
history.

Response — this is a **real, verified** response (not illustrative) from
running backend code against the exact request above, scored with
`xgb-v1-20261106T142923` (the model trained on the real PaySim dataset —
see `docs/model-evaluation.md`):

```json
{
  "transaction_id": "TX-001",
  "risk_score": 0.9903734922409058,
  "risk_level": "high",
  "model_version": "xgb-v1-20261106T142923",
  "threshold": 0.98,
  "explanation": null
}
```

`explanation` is `null` unless `include_explanation: true`, in which case it
is (also a real captured response, for the same request):

```json
{
  "base_value": 0.019822357629617975,
  "contributions": [
    {"feature": "sender_prev_balance", "value": 10000.0, "shap_contribution": 0.2849, "direction": "increases_risk"},
    {"feature": "transaction_type", "value": "TRANSFER", "shap_contribution": 0.2692, "direction": "increases_risk"},
    {"feature": "amount", "value": 8400.0, "shap_contribution": 0.2503, "direction": "increases_risk"},
    {"feature": "recipient_prev_balance", "value": 500.0, "shap_contribution": 0.1667, "direction": "increases_risk"},
    {"feature": "log_amount", "value": 9.036, "shap_contribution": -0.0097, "direction": "decreases_risk"}
  ]
}
```

`ACC-001`/`ACC-002` were never ingested, so this used the documented
new-account defaults (`docs/feature-engineering.md` §3). The model flags
this `TRANSFER` as high risk mainly because it would send 84% of the
sender's balance to a counterparty — a real instance of the balance-
draining pattern real PaySim fraud actually follows
(`docs/model-evaluation.md` §7).

See `docs/model-card.md` for what `base_value`/`shap_contribution` units
mean exactly (probability-space vs. margin-space) and how `risk_level`
bands relate to `threshold`.

Errors: `422` for a malformed request (standard validation path, §0); `503`
`application/problem+json` if no active model artifact is loaded
(`type: .../model-unavailable`); `500` only for a genuine, unexpected
inference failure — never a fabricated score.

### 4.2 Persisted risk scoring — `POST /risk-scores` (Phase 5)

Implemented, full design and examples in `docs/alerts-and-cases.md` §2.
Unlike this section's stateless `/risk/score`, this requires
`transaction_id` to already exist in `app.transactions`, persists the
result (idempotent on `(transaction_id, model_version)`), and creates a
deduplicated `alerts` row when the score crosses the active threshold.

| Method | Path | Role | Description |
|---|---|---|---|
| POST | `/risk-scores` | service | `{transaction_id, include_explanation}` → `{risk_score, alert, created}` |

## 5. Alerts (Phase 5 — implemented)

Field names below match what was actually built
(`docs/alerts-and-cases.md` §1 records the deviations from this
document's original design-time sketch: `alert_type`+`severity`, not a
bare `reason`).

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/alerts` | analyst+ | list, filter by `status`, `severity`, `created_from`/`created_to` |
| GET | `/alerts/{id}` | analyst+ | detail |
| PATCH | `/alerts/{id}` | analyst+ | update `status` (`open`, `triaged`, `escalated`, `dismissed`) |

## 6. Cases and Investigations

**All rows below are implemented**, including the LangGraph investigation
endpoints added in Phase 6 — full design in `docs/alerts-and-cases.md`
§4–5 (cases/evidence) and `docs/investigation-workflow.md`
(investigations).

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/cases` | analyst+ | list, filter by `status`, `assigned_to_user_id` |
| POST | `/cases` | analyst+ | create from one or more `alert_id`s |
| GET | `/cases/{id}` | analyst+ | detail: status, priority, assignment, linked alerts |
| PATCH | `/cases/{id}` | analyst+ | update `status` (never to `resolved` — see below), `priority`, `assigned_analyst_id` |
| POST | `/cases/{id}/decision` | **senior_analyst, admin only** | `{decision, rationale}` → creates `case_decisions` row and moves `status` to `resolved`; `decision` ∈ `confirmed_fraud, not_fraud, dismissed`; `rationale` required, min length 10 |
| GET | `/cases/{id}/decision` | analyst+ | the case's recorded decision, `404` if none yet — Phase 7 addition so the UI can re-show it after a reload |
| POST | `/cases/{id}/evidence` | analyst+ | attach server-resolved evidence (`docs/alerts-and-cases.md` §5) |
| GET | `/cases/{id}/evidence` | analyst+ | list evidence attached to the case, paginated — added in Phase 7 so the case UI can show the evidence trail without the client tracking every id it ever attached |
| GET | `/cases/{id}/investigations` | analyst+ | list investigation-run summaries for the case (`run_id, status, started_by_user_id, revision_count, started_at, completed_at` — no steps/report; use `GET /investigations/{run_id}` for that), paginated — added in Phase 7 for the same reason |
| POST | `/cases/{id}/investigations` | analyst+ | starts a LangGraph run in the background; returns `202` + `{run_id, status: "running"}` immediately |
| GET | `/investigations/{run_id}` | analyst+ | run status, every step (with tool calls), every evidence reference, `draft_report`/`final_report` |
| POST | `/investigations/{run_id}/approve` | analyst+ | finalizes `draft_report` as `final_report` — **not** a case decision (`docs/agent-security.md` §3); idempotent if already `approved` |
| POST | `/investigations/{run_id}/request-revision` | analyst+ | `{feedback}` → re-runs only the report-writing step with accumulated feedback; bounded at 3 rounds, `409` past that |
| POST | `/investigations/{run_id}/reject` | analyst+ | terminal `rejected`; idempotent if already `rejected` |

Approve/reject on a run already in the *other* terminal state return
`409 Conflict` (e.g. approving an already-`rejected` run).

`resolved` is reachable **only** via `POST /cases/{id}/decision` — a
`PATCH /cases/{id}` with `{"status": "resolved"}` is rejected with `422`
regardless of the case's current status, per CLAUDE.md's human-in-the-
loop rule (tested in `backend/tests/test_cases_api.py`).

### 6.1 Investigation detail contract (what `/investigations/{run_id}` exposes)

**Implemented** — `app/schemas/investigation.py::InvestigationDetailResponse`.
Full real example (field-for-field) in `docs/investigation-workflow.md`
§2; shape summary:

```json
{
  "run_id": "uuid", "case_id": "uuid", "started_by_user_id": "uuid",
  "status": "running|awaiting_approval|approved|rejected|revision_requested|failed",
  "model_provider": "mock", "model_name": "mock-deterministic-v1",
  "prompt_version": "v1", "revision_count": 0, "review_feedback": ["string"],
  "draft_report": {
    "summary": "string",
    "hypotheses": [{"text": "string", "confidence": "low|medium|high", "evidence_refs": ["transaction:uuid"]}],
    "uncertainties": ["string"], "recommended_next_step": "string",
    "model_provider": "string", "model_name": "string", "is_mock": true,
    "evidence_refs": ["transaction:uuid", "account:uuid"]
  },
  "final_report": null,
  "error": null, "started_at": "2026-01-01T00:00:00Z", "completed_at": null,
  "steps": [
    {"node_name": "evidence_collector", "attempt": 1, "status": "succeeded",
     "tool_calls": [{"tool": "get_transaction", "args_summary": {"transaction_id": "uuid"}, "result_ref": "found", "duration_ms": 1.2}],
     "output": {}, "error": null, "started_at": "...", "completed_at": "..."}
  ],
  "evidence_refs": [
    {"evidence_type": "transaction", "source_reference": "transaction:uuid", "summary": "string", "collected_by_node": "evidence_collector", "created_at": "..."}
  ]
}
```

Every element of `hypotheses[].evidence_refs` must resolve to a real
`source_reference` collected in this run — validated in code
(`app/agents/graph.py::report_writer_node`), not merely by a schema
shape check; a citation outside the collected set is dropped before the
draft is ever returned to the client. See `docs/multi-agent-architecture.md`
§3.

### 6.2 Read-only agent tools (internal contract, not HTTP, but documented here since it's part of the agent/API boundary)

**Implemented** — `app/agents/tools.py`; full detail including the
explicit per-agent permission allow-list in `docs/agent-tools.md`.

| Tool | Backed by | Returns |
|---|---|---|
| `get_transaction(transaction_id)` | `app.transactions` | transaction fields, no label |
| `get_account_profile(account_id, as_of_step)` | `app.accounts`, `app.transactions` | aggregates as of a step, chronologically bounded |
| `get_graph_neighborhood(account_id, hops, as_of_step)` | `app/services/graph_analytics.py` | same shape as §2's neighborhood response |
| `get_graph_metrics(account_id, as_of_step)` | `app/services/graph_analytics.py` | same shape as §2.1's metrics response |
| `get_fund_flow(account_id, as_of_step, max_hops, max_branches)` | `app/services/graph_analytics.py` | same shape as §2.1's fund-flow response |
| `get_risk_score(transaction_id)` | `app.risk_scores` | score, no label |
| `get_shap_explanation(transaction_id)` | `app.risk_scores.shap_values` | SHAP contributions, no label |
| `get_similar_past_cases(case_id)` | `app.cases`, `app.case_decisions` | past **human decisions** on cases sharing a counterparty account — analyst history, not PaySim ground truth (see `docs/agent-tools.md` §4 for exactly what "similar" means here) |

All eight run under the `api_service` DB role (§3 of `docs/database-design.md`);
none can reach `ground_truth` even if a future tool's query had a bug. Each
agent may only call a fixed subset — `app/agents/tools.py::AGENT_TOOL_PERMISSIONS`
— enforced at every call, not just at wiring time (`docs/agent-tools.md`).

## 7. Audit (Phase 5 — implemented)

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/audit-log` | admin | filter by `user_id`, `action`, `occurred_from`/`occurred_to` date range |

See `docs/alerts-and-cases.md` §6 for exactly which actions are logged
and `docs/authentication.md` for the auth events.

## 8. Health

| Method | Path | Role | Description |
|---|---|---|---|
| GET | `/health` | none | liveness |
| GET | `/health/ready` | none | readiness: DB connection + active model artifact loadable |

## 9. Versioning

The `/api/v1` prefix is the only versioning mechanism for now; a breaking change
ships as `/api/v2` rather than mutating `v1` behavior, so the frontend and any
documented contract never silently drift.
