# SentinelAI — Investigation Workflow (Phase 6 Part F)

Status: **implemented and tested** end-to-end against a real database
(`backend/tests/test_investigations_api.py`). This is the analyst-facing
API walkthrough; see `docs/multi-agent-architecture.md` for how it's
built and `docs/agent-security.md` for the security posture.

## 1. Starting an investigation

```
POST /api/v1/cases/{case_id}/investigations
Authorization: Bearer <analyst/senior_analyst/admin JWT>
```

Requires the case to exist and to have at least one linked alert
(`CaseAlert`) — `intake_node` raises if there's nothing to investigate.
Returns **immediately** (`202 Accepted`):

```json
{"run_id": "<uuid>", "status": "running"}
```

The actual LangGraph execution runs in a background thread
(`docs/multi-agent-architecture.md` §2.5) — this call never blocks on
evidence retrieval, graph analysis, or the LLM call.

## 2. Checking status / reviewing steps and evidence

```
GET /api/v1/investigations/{run_id}
Authorization: Bearer <analyst/senior_analyst/admin JWT>
```

```json
{
  "run_id": "...", "case_id": "...", "started_by_user_id": "...",
  "status": "awaiting_approval",
  "model_provider": "mock", "model_name": "mock-deterministic-v1",
  "prompt_version": "v1", "revision_count": 0, "review_feedback": [],
  "draft_report": {
    "summary": "...", "hypotheses": [{"text": "...", "confidence": "medium", "evidence_refs": ["transaction:...", "account:..."]}],
    "uncertainties": ["..."], "recommended_next_step": "...",
    "model_provider": "mock", "model_name": "mock-deterministic-v1", "is_mock": true,
    "evidence_refs": ["transaction:...", "account:...", "..."]
  },
  "final_report": null,
  "error": null, "started_at": "...", "completed_at": null,
  "steps": [
    {"node_name": "intake", "attempt": 1, "status": "succeeded", "tool_calls": [], "output": {...}, "started_at": "...", "completed_at": "..."},
    {"node_name": "evidence_collector", "attempt": 1, "status": "succeeded", "tool_calls": [{"tool": "get_transaction", "args_summary": {...}, "result_ref": "found", "duration_ms": 1.2}], "output": {...}},
    {"node_name": "network_investigator", "attempt": 1, "status": "succeeded", "tool_calls": [...]},
    {"node_name": "report_writer", "attempt": 1, "status": "succeeded", "tool_calls": []},
    {"node_name": "human_approval_gate", "attempt": 1, "status": "succeeded", "tool_calls": []}
  ],
  "evidence_refs": [
    {"evidence_type": "transaction", "source_reference": "transaction:...", "summary": "TRANSFER of 8400.00 at step 10 (... -> ...)", "collected_by_node": "evidence_collector"},
    {"evidence_type": "historical_stats", "source_reference": "account:...", "summary": "Account ...: 0 prior txns, 0 unique recipients", "collected_by_node": "evidence_collector"},
    {"evidence_type": "network_finding", "source_reference": "account:...", "summary": "Account has 0 incoming / 1 outgoing txns (fan_in=False, fan_out=False)", "collected_by_node": "network_investigator"}
  ]
}
```

While `status == "running"`, `steps`/`evidence_refs` show whatever has
completed so far — poll this endpoint rather than assuming completion.
`final_report` stays `null` until a human approves (§4).

## 2.1 Listing a case's investigation history

```
GET /api/v1/cases/{case_id}/investigations
Authorization: Bearer <analyst/senior_analyst/admin JWT>
```

Phase 7 addition: paginated summaries (`run_id, case_id,
started_by_user_id, status, revision_count, started_at, completed_at`)
for every run on the case — no `steps`/`evidence_refs`/`draft_report`,
to keep the list cheap; a caller wanting a run's full detail still goes
to `GET /investigations/{run_id}` (§2) for that one run.

## 3. The status machine

```
running ──► awaiting_approval ──► approved
                  │     ▲
                  │     └── request-revision (≤3 times)
                  ▼
              rejected
```

`running` → `failed` is also possible (an unrecoverable node error after
retries are exhausted — `AgentRun.error` holds the exception message).
`approved`/`rejected` are terminal. Approving or rejecting an
already-terminal run of the *same* outcome is idempotent (`200`,
no-op); the *other* terminal action on an already-terminal run is a
`409 Conflict`.

## 4. Human review actions

```
POST /api/v1/investigations/{run_id}/approve
POST /api/v1/investigations/{run_id}/reject
POST /api/v1/investigations/{run_id}/request-revision
{"feedback": "Please double-check whether the fan-in pattern also appears on the destination account."}
```

**Approving finalizes the draft as the case's investigation record** —
`final_report` is set, `status` becomes `approved`. **This is not a
case decision.** It never changes `Case.status` and never creates a
`CaseDecision` row (`docs/agent-security.md` §3) — resolving the case
itself still only ever happens through the Phase 5 endpoint:

```
POST /api/v1/cases/{case_id}/decision   (senior_analyst/admin only)
{"decision": "confirmed_fraud"|"not_fraud"|"dismissed", "rationale": "<min 10 chars>"}
```

**Requesting a revision** re-runs only the report-writing step (not a
full re-investigation — the already-collected evidence/findings are
reused) with the accumulated feedback, and returns the *updated* draft
in the same response. Bounded at 3 rounds
(`app/db/models/agent_run.py::MAX_REVISION_ROUNDS`); a 4th request
returns `409`.

## 5. A complete walkthrough (what was actually run and observed)

This is the exact sequence `tests/test_investigations_api.py::
test_full_investigation_lifecycle_evidence_to_report_to_approval` runs
against a real database, and what the final report section of this
phase's completion report demonstrates:

1. Ingest one balance-draining `TRANSFER` (service credential), creating
   a `manual` alert and a `Case` (`priority="high"`, `status="open"`).
2. `POST /cases/{id}/investigations` as an `analyst` → `202`,
   `{run_id, status: "running"}`.
3. Poll `GET /investigations/{run_id}` until `status ==
   "awaiting_approval"` — observed node sequence: `intake` →
   `evidence_collector` (5 tool calls: the transaction, its risk score
   if any, SHAP if any, both accounts' historical stats, similar past
   cases) → `network_investigator` (4 tool calls: graph metrics +
   neighborhood for each of the two accounts) → `report_writer` (0
   tool calls — operates only on what the prior two nodes collected) →
   `human_approval_gate`. All five steps `succeeded` on attempt 1.
4. `draft_report.evidence_refs` includes `transaction:<the real id>` —
   every hypothesis (none were generated in this particular run, since
   neither the score nor the structural metrics were flagged) would
   have had to cite only ids from this list or be dropped.
5. `POST /investigations/{run_id}/approve` as the same analyst → `200`,
   `final_report` now equals the draft. `Case.status` re-checked
   directly against the database: still `"open"` — unaffected.

## 6. Known limitations

- No pagination on `steps`/`evidence_refs` within
  `GET /investigations/{run_id}` — acceptable at this phase's run sizes
  (typically under 15 steps, under 20 evidence refs per run); would need
  it for a production case with hundreds of linked alerts.
- No webhook/notification when a run reaches `awaiting_approval` —
  an analyst must poll. A real deployment would want a push notification
  here; out of scope for this phase (no message queue in the approved
  stack — `docs/multi-agent-architecture.md` §2.5).
