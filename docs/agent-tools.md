# SentinelAI — Agent Tools (Phase 6)

Status: **implemented and tested** (`backend/tests/test_agent_tool_permissions.py`,
plus exercised end-to-end in `backend/tests/test_investigations_api.py`).
Extends the tool contract `docs/api-contracts.md` §6.2 sketched at
design time with what was actually built and where it differs.

## 1. Every tool runs under `api_service` — never a separate agent role

There is no "agent" database credential. Every function in
`app/agents/tools.py` takes the same `db: Session` the rest of the
backend uses, bound to the `api_service` role
(`app/db/session.py`/`docs/database-design.md` §3) — the same role that
has no `GRANT` on `ground_truth` at all. An agent is therefore
structurally incapable of reaching ground truth or acting with elevated
privilege; this isn't a check that could be bypassed by a bug in
`app/agents/`, it's the same database-layer wall every other part of
this backend is already behind. Verified by
`tests/test_agent_security.py::test_agent_tools_module_never_references_ground_truth`
(no `ground_truth` schema/table reference exists in the module at all)
and by the pre-existing `tests/test_security_isolation.py` (the DB-grant
layer itself, unaffected by this phase's new tables).

## 2. The tools

| Tool | Agent | Backed by | Returns |
|---|---|---|---|
| `get_transaction(transaction_id)` | Evidence Collector | `app.transactions` | transaction fields, no label |
| `get_account_profile(account_id, as_of_step)` | Evidence Collector | `app.accounts` + `app/services/history.py` | aggregates strictly before `as_of_step` |
| `get_risk_score(transaction_id)` | Evidence Collector | `app.risk_scores` | latest persisted score, or `None` if never scored |
| `get_shap_explanation(transaction_id)` | Evidence Collector | `app.risk_scores.shap_values` | stored SHAP contributions, or `None` if none were computed |
| `get_similar_past_cases(case_id)` | Evidence Collector | `app.cases`/`case_alerts`/`case_decisions` | past **human decisions** on cases sharing a counterparty account |
| `get_graph_neighborhood(account_id, hops, as_of_step)` | Network Investigator | `app/services/graph_analytics.py` | same shape as `GET /graph/accounts/{id}` |
| `get_graph_metrics(account_id, as_of_step)` | Network Investigator | `app/services/graph_analytics.py` | same shape as `GET /graph/accounts/{id}/metrics` |
| `get_fund_flow(account_id, as_of_step, max_hops, max_branches)` | Network Investigator | `app/services/graph_analytics.py` | same shape as `GET /graph/accounts/{id}/fund-flow` |

Deviations from `docs/api-contracts.md` §6.2's original sketch:

- `get_risk_score` and `get_shap_explanation` are two tools, not one —
  Part B of this phase's brief asked for "retrieve persisted XGBoost
  scores" and "retrieve SHAP explanations" as separate bullets, so each
  got its own tool, both reading the same `RiskScore` row (one field
  each) rather than always returning both together.
- The three graph tools map 1:1 onto the already-implemented Phase 4
  `/graph/*` endpoints' underlying service functions
  (`app/services/graph_analytics.py`) — no new graph algorithm was
  written for this phase; Agent 2 calls exactly the same, already-tested
  NetworkX code the API routes call.
- `get_similar_past_cases`'s actual similarity rule (shared counterparty
  account) is simpler than "structurally similar" might imply — see §4.

## 3. Evidence that doesn't resolve is never fabricated

Every tool raises `EvidenceNotFound` (not a placeholder, not a zero-
filled stand-in) when its id doesn't resolve to a real row —
`get_transaction` on a nonexistent id, `get_graph_neighborhood` on a
nonexistent account, etc. `evidence_collector_node`/
`network_investigator_node` catch this per-item and skip it (one missing
transaction doesn't abort the whole run), but the tool itself never
invents a result. `get_risk_score`/`get_shap_explanation` return `None`
(not `EvidenceNotFound`) for "this transaction exists but was never
scored" — a different, equally honest fact: the transaction is real,
the score just doesn't exist yet.

## 4. `get_similar_past_cases` — what "similar" actually means here

The heuristic is deliberately simple: another case counts as similar if
any of its alerted transactions shares an origin or destination account
with the current case's alerted transactions, **and** that other case
has at least one recorded `CaseDecision`. This is analyst history (a
record of what a human actually decided before), never PaySim ground
truth — `app.case_decisions` has no relationship to `ground_truth` at
all. It is not a learned embedding or a fraud-pattern classifier; every
result carries `"similarity_basis": "shares a counterparty account with
this case's alerted transactions"` so nothing downstream (the report, an
analyst reading it) can mistake "shares an account" for "is
structurally similar in some deeper sense this system actually
verified."

The returned `rationale` is the deciding analyst's own free text —
genuine evidentiary value, but untrusted input. See
`docs/agent-security.md` §4 for how it's handled once it reaches the
report-writing step.

## 5. Tool versioning

`app/agents/tools.py::TOOL_VERSIONS` records a version string per tool
(all `"v1"` as of this phase), copied onto every `AgentRun.tool_versions`
at start time (Part E: "record ... tool versions"). Bump the relevant
entry whenever a tool's query or output shape changes, so a later audit
of an old run can tell whether a given tool's *current* behavior still
matches what actually produced that run's evidence.
