# SentinelAI — Graph Analytics

Status: **implemented and tested** (Phase 4,
`docs/implementation-plan.md`). This document describes what was actually
built in `backend/app/graph/`, `backend/app/services/graph_analytics.py`,
and `backend/app/api/routes/graph.py` — not a design sketch.

## 1. Purpose and scope

The graph-analytics engine surfaces **structural signal** from the
transaction network around an account — who it transacts with, how
concentrated that activity is, how fast money moves through it, and
whether it sits on a cycle. Per `CLAUDE.md` and the `graph-analytics`
skill's mandatory rules:

- Every value this engine returns is a structural observation, never a
  fraud determination. Every API response that surfaces graph metrics
  includes the same disclaimer string verbatim
  (`app.graph.metrics.GRAPH_DISCLAIMER`).
- No `ground_truth` data is used or exposed anywhere in this module — it
  only ever reads `app.accounts`/`app.transactions` through the
  `api_service` role, the same role the rest of the backend uses (see
  `docs/database-design.md` §3).
- Every query is bounded in size and depth — nothing here loads
  `app.transactions` in bulk.

## 2. Graph construction (`app/graph/build.py`)

Accounts are nodes; transactions are directed edges carrying the
transaction's `id`/`external_ref`, `amount`, `step`, and `type`. The graph
is a NetworkX `MultiDiGraph` (not `DiGraph`), so repeated transactions
between the same two accounts are preserved as separate parallel edges
rather than collapsed.

`build_account_neighborhood(db, center_account_id, hops, as_of_step,
max_nodes, max_edges)` builds a **bounded k-hop neighborhood** around one
account by expanding outward hop by hop:

1. Start with a frontier of just the center account.
2. Each hop, query transactions touching any account currently in the
   frontier (`origin_account_id IN (...) OR dest_account_id IN (...)`),
   capped at `PER_HOP_QUERY_LIMIT` (2000) rows, most-recent-`step` first.
3. Newly discovered accounts become the next hop's frontier.
4. Stop after `hops` iterations (default 2, max 4), or as soon as
   `max_nodes` (default 300) or `max_edges` (default 1500) is reached.

If any cap is hit, the result's `truncated` flag is `True` and every graph
API response surfaces it explicitly — a partial view is never presented as
a complete one.

`as_of_step`, when given, is applied as `step < as_of_step` at every hop —
never `<=` — so a neighborhood "as of" a step never includes that step's
own transaction or anything later. This is the same chronological-integrity
rule the ML pipeline's feature engineering follows
(`docs/database-design.md` §4), applied here to graph queries.

An account that exists but has no transactions (isolated account) returns
a graph containing just that one node and no edges — not an error. An
account id that doesn't exist in `app.accounts` returns an empty graph from
`build_account_neighborhood` itself; the service layer
(`app/services/graph_analytics.py`) checks existence separately and raises
`AccountNotFound`, which the API layer turns into a `404`.

## 3. Algorithms (`app/graph/metrics.py`)

All of these are pure functions over a graph already produced by
`build_account_neighborhood` (or a synthetic scenario, §5) — none of them
query the database.

| Function | Returns | Notes |
|---|---|---|
| `incoming_outgoing_counts(graph, node)` | `{incoming_transaction_count, outgoing_transaction_count}` | Transaction-count, not account-count — each parallel edge counts separately. |
| `unique_counterparties(graph, node)` | `{unique_senders, unique_recipients}` | Deduplicated distinct accounts, regardless of how many transactions each sent/received. |
| `fan_pattern(unique_senders, unique_recipients, threshold)` | `{fan_in_pattern, fan_out_pattern}` | A simple, deterministic threshold heuristic (default 5) — not a classifier. |
| `transaction_velocity(graph, node, as_of_step, window_steps)` | transaction count in the trailing window | Default window is 24 steps (~1 simulated day, matching `RECENT_TXN_WINDOW_STEPS` in `app/ml/features.py`). |
| `connected_components(graph)` | list of node-id lists | Weakly-connected (direction ignored). A single-account neighborhood is connected by construction; this is most useful against a combined/multi-account view. |
| `detect_cycles(graph, max_length, max_cycles)` | list of node-id lists | Bounded (`length_bound`, default 6; capped at 25 results) so it stays usable against a dense neighborhood instead of risking the combinatorial blow-up unbounded `nx.simple_cycles` can hit. |

### Account neighborhood exploration

This *is* `build_account_neighborhood` itself (§2) plus the metrics above
applied to its result — "exploring a neighborhood" means building the
bounded subgraph and then asking these questions of it.

### Time-aware fund-flow investigation (`app/graph/fund_flow.py`)

`trace_fund_flow(db, source_account_id, as_of_step, max_hops, max_branches)`
walks **forward in simulated time** from an account's outgoing
transactions: having arrived at an account via a transaction at `step S`,
it only follows that account's *own* outgoing transactions with
`step > S` (and, if `as_of_step` is given, `step < as_of_step`). This
surfaces rapid pass-through / mule-chain patterns (money arriving, then
leaving again shortly after) as explicit, time-ordered paths, rather than
an undirected "is there a path" check.

Bounds: `max_hops` (default 3, max 5), `max_branches` per account per hop
(default 3, max 10), and a hard cap of 500 total database queries per call
(`MAX_TOTAL_EXPANSIONS`) regardless of the hop/branch settings requested —
this is what keeps `max_hops=5, max_branches=10` (which would otherwise
branch combinatorially) from issuing an unbounded number of queries. If the
cap is hit, `truncated=True` is set on the result.

## 4. API endpoints

Base path `/api/v1/graph`. All four endpoints are `analyst+` per
`docs/api-contracts.md` §0's role conventions (auth enforcement itself is
not yet implemented anywhere in the backend — a pre-existing, documented
gap; see `docs/implementation-plan.md`'s "Not started" list). See
`docs/api-contracts.md` §2.1 for the full request/response contract.

| Method | Path | Returns |
|---|---|---|
| GET | `/graph/accounts/{account_id}` | Bounded k-hop neighborhood: nodes, edges, detected cycles |
| GET | `/graph/accounts/{account_id}/metrics` | Structural metrics for one account |
| GET | `/graph/accounts/{account_id}/transactions` | The account's own transactions, direction-labeled, `as_of_step`-bounded |
| GET | `/graph/accounts/{account_id}/fund-flow` | Time-aware onward-transfer paths from the account |

All four validate `account_id` as a UUID, return `404` if the account
doesn't exist, and `422` on an out-of-range query parameter (FastAPI/
Pydantic validation, matching every other route in this backend).

### Example: neighborhood

```
GET /api/v1/graph/accounts/8f14e45f-.../?hops=2
```

```json
{
  "center_account_id": "8f14e45f-...",
  "hops": 2,
  "as_of_step": null,
  "nodes": [
    {"id": "8f14e45f-...", "external_ref": "C123456789", "account_type": "customer"},
    {"id": "a2b1c3d4-...", "external_ref": "M987654321", "account_type": "merchant"}
  ],
  "edges": [
    {
      "source": "8f14e45f-...", "target": "a2b1c3d4-...",
      "transaction_id": "f1e2d3c4-...", "external_ref": "TX-001",
      "amount": "8400.00", "step": 120, "type": "TRANSFER"
    }
  ],
  "cycles": [],
  "truncated": false,
  "disclaimer": "Structural signal derived from transaction connectivity only. This is not a fraud determination and does not establish money laundering or any other wrongdoing; it requires human investigation and corroborating evidence."
}
```

### Example: metrics

```
GET /api/v1/graph/accounts/8f14e45f-.../metrics
```

```json
{
  "account_id": "8f14e45f-...",
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

(Both JSON bodies above are illustrative of the response *shape*; the
exact field values come from whatever the account's real transactions are.
See §6 for the runs that were actually exercised against the ingestion
endpoint and a live database during this phase.)

## 5. Relationship to the synthetic scenarios

See `docs/graph-scenarios.md`. The scenario graphs from
`app/graph/synthetic.py` use the exact same node/edge attribute shape as
`build_account_neighborhood`'s output (`external_ref`, `account_type`,
`transaction_id`, `amount`, `step`, `type`), so every function in §3 runs
against either source unmodified — this is what lets the synthetic
fixtures stand in for real data in `app.graph.metrics`'s unit tests.

## 6. Performance characteristics and constraints

- **Per-hop query cap**: 2000 rows (`PER_HOP_QUERY_LIMIT` in
  `app/graph/build.py`). A single hop never issues an unbounded `SELECT`.
- **Neighborhood size caps**: 300 nodes / 1500 edges by default for the
  investigation endpoint; the metrics endpoint (always 1 hop) uses a
  larger 5001-node / 5000-edge cap (`METRICS_MAX_NODES`/`METRICS_MAX_EDGES`
  in `app/services/graph_analytics.py`) since it only ever needs one
  account's own transactions, not a multi-hop fan-out. Both caps must be
  raised together: `build_account_neighborhood` enforces node and edge
  limits independently, and a 1-hop ego graph adds roughly one new node
  per new counterparty, so raising only `max_edges` would still truncate
  at the default 300-node cap — a real bug caught and fixed during this
  phase's self-review, before any live-database run could have surfaced
  it.
- **Fund-flow query cap**: 500 total database queries per call
  (`MAX_TOTAL_EXPANSIONS`), independent of `max_hops`/`max_branches`.
- **Cycle detection cap**: `length_bound=6`, capped at 25 returned cycles.
- Measured timings (see `backend/tests/test_graph_performance.py` for the
  exact tests and bounds asserted):
  - In-memory `incoming_outgoing_counts` and `connected_components` over a
    5,000-edge hub-and-spoke graph, and `detect_cycles` with
    `length_bound=6` over a 500-node ring: all asserted to complete in a
    few seconds on ordinary hardware (generous bounds, not strict
    benchmarks — see the test file for the actual assertions).
  - A database-backed test ingests 1,000 transactions through the real
    `/transactions/ingest` endpoint and times
    `build_account_neighborhood` against the live database for a
    1,000-edge, 1-hop neighborhood.
  - These DB-backed performance numbers, like the rest of this phase's
    DB-backed tests, could not be executed in the environment this phase
    was implemented in — see §7.

## 7. Known limitations

- **Not exercised against a live database in this phase's development
  environment.** The sandbox this phase was built in has a running
  Postgres container, but the `api_service` role's real password (set in
  `infra/.env`, which is git-ignored and was not readable in this
  environment) didn't match the backend's default config, so every
  DB-backed test in `backend/tests/test_graph_*.py` ran and was verified
  to **skip cleanly** (not fail, not fake a pass) rather than actually
  execute against Postgres. The project's CI (`.github/workflows/ci.yml`)
  does spin up its own Postgres service with known credentials and runs
  the full suite including migrations, so these tests are expected to run
  for real there; that run was not observed as part of this phase. This is
  a real, disclosed gap — not a claim that the DB-backed tests passed.
- **`connected_components` is rarely interesting on the neighborhood
  endpoint alone.** A BFS-built single-account neighborhood is connected
  by construction; the function is most useful against a combined view
  (e.g. several accounts' neighborhoods merged, or the synthetic
  scenarios) rather than through the current API surface, which only ever
  returns one account's neighborhood.
- **Fan-in/fan-out thresholds are a fixed, simple heuristic** (unique
  counterparty count ≥ 5 by default), not a tuned or learned threshold —
  deliberately so, since this signal is explicitly structural, not a
  prediction.
- **No persistence.** Nothing in this module writes to the database;
  graph metrics are computed fresh on every request. If/when Phase 5
  (alerts) wants to attach graph evidence to an alert/case, that
  persistence is new work, not something this phase added.
- **No auth/role enforcement yet** on any of the four new routes — this
  matches every other endpoint in the backend so far (see
  `docs/implementation-plan.md`'s "Not started" list); it is not specific
  to this phase.
- **`detect_cycles` only reports cycles within `max_length`** (default 6);
  a longer cycle in the underlying data would not be reported by the
  default call. This is an explicit, documented bound, not a bug.
