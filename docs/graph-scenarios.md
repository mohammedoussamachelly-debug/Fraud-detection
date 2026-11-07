# SentinelAI — Synthetic Graph Scenarios

Status: **implemented and tested** (Phase 4). Generators live in
`backend/app/graph/synthetic.py`; tests in
`backend/tests/test_graph_synthetic.py`.

## 1. Why synthetic scenarios exist

`docs/model-evaluation.md` §1 reports that in the real PaySim dataset,
**unique senders have a mean of 1.00 transactions per sender** —
essentially every account sends at most once. That is exactly the right
shape for training a per-transaction fraud classifier (Phase 3), but it
means real PaySim data contains almost no repeated-sender structure for a
*network*-analysis engine to find: there's very little fan-in, fan-out,
chaining, or cycle structure actually present to exercise against.

So, per this phase's mission brief, the structural-pattern algorithms in
`app/graph/metrics.py` are exercised against **hand-specified, deterministic
synthetic graphs** instead of (or in addition to) whatever limited
structure exists in real ingested data. These graphs are built directly in
Python — never derived from PaySim, never written to the database, and
never ingested through `/transactions/ingest`.

**These scenarios are not evidence of real fraud, and no structural
pattern they contain proves money laundering.** They exist solely to give
the structural-pattern detectors in `app/graph/metrics.py` known,
predictable topologies to be tested against. Every scenario graph carries
`graph.graph["synthetic"] = True` plus a `scenario` name and `description`,
so nothing downstream can mistake one for real data.

## 2. Scenarios

All four are registered in `app.graph.synthetic.SCENARIOS` and built via
`build_scenario(name)`. Every edge's account ids and transaction ids are
fixed strings (e.g. `SYN-M2O-SRC-00`, `SYN-M2O-TX-00`) — there is no
database row behind them, and no randomness: calling a generator twice
produces an identical graph (`test_scenarios_are_deterministic`).

### 2.1 `many_to_one_concentration`

`N` distinct sender accounts (`SYN-M2O-SRC-00` … `SYN-M2O-SRC-{N-1}`) each
send exactly one transaction to a single hub account (`SYN-M2O-HUB`).
Structurally: `unique_senders(HUB) == N`, `unique_recipients(HUB) == 0`,
and `fan_pattern` reports `fan_in_pattern=True` once `N` reaches the
default threshold (5). This represents a many-to-one concentration
("smurfing"-style aggregation) pattern — a *shape*, not a verdict.

### 2.2 `one_to_many_redistribution`

The mirror image: a single source account (`SYN-O2M-SRC`) distributes
funds to `N` distinct recipients (`SYN-O2M-DST-00` … `SYN-O2M-DST-{N-1}`).
`fan_pattern` reports `fan_out_pattern=True` for the source once `N`
reaches the threshold.

### 2.3 `rapid_onward_transfers`

A chain of `chain_length + 1` accounts (`SYN-CHAIN-00` → `SYN-CHAIN-01` →
… → `SYN-CHAIN-{chain_length}`), each transaction occurring one simulated
step after the previous, with a fixed 5% skim at each hop (deterministic,
not randomized — `amount = round(amount * 0.95, 2)`). Every intermediate
account has in-degree 1 and out-degree 1: money arrives and leaves once.
This is the shape `app.graph.fund_flow.trace_fund_flow` is designed to
surface against real data — a path where each hop's `step` strictly
increases.

### 2.4 `circular_transfers`

`cycle_length` accounts (`SYN-RING-00` … `SYN-RING-{cycle_length-1}`)
arranged in a closed loop, each sending to the next and the last sending
back to the first. `app.graph.metrics.detect_cycles` finds exactly one
cycle, containing every node in the ring. Requires `cycle_length >= 3`.

## 3. Reproducing a scenario

```python
from app.graph.synthetic import build_scenario, SCENARIOS

graph = build_scenario("circular_transfers")  # or any key in SCENARIOS
print(graph.graph["scenario"], graph.graph["description"])
print(list(graph.edges(data=True)))
```

Each generator also accepts its sizing parameter directly for a custom
size (e.g. `many_to_one_concentration(num_senders=20)`); `build_scenario`
always uses each generator's default size.

## 4. How these differ from the live API

The synthetic scenarios are a **testing/demonstration fixture**, not an
API-reachable feature — there is no endpoint that serves a synthetic
scenario. They're consumed directly by
`backend/tests/test_graph_synthetic.py`, which asserts that
`app.graph.metrics`'s functions (`unique_counterparties`, `fan_pattern`,
`detect_cycles`) report the expected result against each known topology.
This is what lets the test suite assert on *known, predictable* structural
output (per `docs/implementation-plan.md` Phase 4's exit criteria) even
though real PaySim data rarely contains these patterns.

## 5. Known limitations

- Fixed, small default sizes (8 senders/recipients, a 5-account chain, a
  4-account ring) — large enough to cross the default fan-in/fan-out
  threshold (5) and to exercise cycle detection, not large enough to be a
  load test (see `docs/graph-analytics.md` §6 for the actual performance
  tests, which use separately hand-built large graphs, not these
  scenarios).
- No "mixed" or "noisy" scenario (e.g. a concentration pattern embedded in
  otherwise-ordinary traffic) — each scenario is a single, isolated
  pattern, intentionally, to keep the expected test output unambiguous.
- These graphs are never persisted to Postgres and are not reachable
  through any API endpoint; using one as a demo requires calling
  `app.graph.synthetic` directly from Python (§3), not an HTTP request.
