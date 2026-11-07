# SentinelAI — Alerts, Cases, Evidence & Audit (Phase 5)

Status: **implemented and tested** against a real PostgreSQL database.
124 backend tests pass (0 failed, 0 skipped) with this phase added —
see the final Phase 5 report for the exact breakdown.

This phase adds persistent risk scores, fraud alerts, investigation
cases, structured evidence, and audit logging on top of Phase 3's
stateless scoring (`POST /risk/score`) and Phase 4's graph analytics.
`docs/database-design.md` §2 already sketched this schema at design
time; this document records what was actually built, including the
several places implementation deviated from that sketch — each one
explained below rather than silently diverging from the written design.

## 1. Entities

New tables, all in the `app` schema (migration `0004`,
`backend/alembic/versions/0004_alerts_cases_evidence_audit.py`):

| Table | Purpose |
|---|---|
| `users` | Authenticated humans — see `docs/authentication.md` |
| `risk_scores` | One row per (transaction, model_version) scoring result |
| `alerts` | A transaction crossing a review threshold or rule |
| `cases` | An investigation grouping one or more alerts |
| `case_alerts` | Join table: case ↔ alert |
| `case_decisions` | The human-in-the-loop record that resolves a case |
| `case_evidence` | A server-resolved snapshot of supporting evidence |
| `audit_log_entries` | Append-only log of every auth/case/evidence/scoring action |

### Deviations from `docs/database-design.md`'s original sketch

The design doc (written before Phase 2–4 existed) used different field
names in a few places; implementation follows this doc, not that one,
where they conflict — `database-design.md` should be read as superseded
on these points (see its Phase 5 update note):

- `alerts.alert_type`/`severity` (not `reason` alone) — `severity` is new,
  requested explicitly by this phase's brief, since "crossed the
  threshold" and "how badly" are different facts a triage queue needs.
- `cases.assigned_analyst_id` (not `assigned_to_user_id`), plus new
  `priority` and `closed_at` columns.
- `case_evidence` replaces the design doc's `case_notes` — see §4 below;
  an analyst note is *one kind* of evidence (`evidence_type="analyst_note"`)
  rather than a second, parallel table.
- `case_decisions` was **not** in this phase's brief's explicit table
  list, but is included anyway: CLAUDE.md's Security Rules are explicit
  and non-negotiable — "no code path marks a case resolved,
  confirmed-fraud, or dismissed without a recorded analyst/approver
  decision" — and `database-design.md` already specified this exact
  table. Omitting it would have left `Case.status="resolved"" reachable
  with no accountable row behind it.
- `audit_log_entries` (not a separate `audit_events` table) — same
  design, this codebase's pre-existing name; `entity_type`/`entity_id`
  is a generic polymorphic reference rather than a dedicated `case_id`
  column, so one table covers case-scoped events (`entity_type="case"`)
  and non-case events (`login`, with no entity at all) uniformly.
- `model_versions` from the design doc does **not** exist as a table.
  `risk_scores.model_version` is a plain string (the artifact's
  `version_label`, e.g. `xgb-v1-20261106T142923`), matching the
  convention `app/ml/inference.py` already established in Phase 3 —
  introducing a `model_versions` FK table this codebase has never had
  would have been a bigger change than this phase asked for.

## 2. Risk score persistence — `POST /risk-scores`

`service`-role only (same principal as `POST /transactions/ingest`).
Unlike the stateless `POST /risk/score` (§4.1 of `docs/api-contracts.md`),
this endpoint requires `transaction_id` to already be a real row in
`app.transactions` — every scoring input (amount, type, balances,
sender/receiver) is read from that row, never resupplied by the caller,
so a persisted score can never be computed from facts that don't match
what was actually ingested.

```
POST /api/v1/risk-scores
Authorization: Bearer <SERVICE_API_KEY>
{"transaction_id": "<uuid>", "include_explanation": true}
```

It reuses the exact Phase 3 pipeline (`app/services/risk_scoring.py::
score_transaction` → `app/ml/features.py` → `app/ml/inference.py`) —
the leakage-safety guarantees (pre-event history only) carry over
unchanged; this phase added no second way to compute a feature row.

**Idempotency**: a unique constraint on `(transaction_id, model_version)`
means re-scoring the same transaction with the same active model version
returns the existing row (`created: false`) rather than a duplicate. A
concurrent duplicate request is resolved at the database layer (the
losing insert catches the `IntegrityError` and re-selects) — verified in
`tests/test_risk_score_persistence.py::
test_persist_is_idempotent_for_same_transaction_and_model_version`.
Re-scoring under a *different* model version creates a new row, since a
different model's score is a different, independently meaningful fact.

**Alert creation**: if `risk_level == "high"` (the same relative-to-
threshold band `app/ml/inference.py::risk_level_for_score` already
computes — no new hardcoded score), an `alerts` row is created with
`alert_type="model_threshold"` and a severity derived from how far above
the threshold the score landed (`app/services/alerting.py::
severity_for_score` — `"critical"` only past the midpoint of the
remaining headroom to 1.0, still relative to the active threshold, never
an absolute magic number). A unique constraint on
`(transaction_id, alert_type)` prevents a duplicate alert on repeat
scoring.

**Explanation evidence**: when `include_explanation: true`, the SHAP
contributions are stored on `risk_scores.shap_values` at scoring time —
not recomputed later — so attaching it as case evidence (§4) never needs
to reload a possibly-rotated model artifact.

## 3. Alerts

| Method | Path | Role |
|---|---|---|
| `GET` | `/alerts` | analyst+ |
| `GET` | `/alerts/{id}` | analyst+ |
| `PATCH` | `/alerts/{id}` | analyst+ |

`GET /alerts` filters by `status`, `severity`, and a `created_from`/
`created_to` date range; paginated (`limit`/`offset`, same convention as
every other list endpoint). `PATCH /alerts/{id}` accepts
`{"status": "triaged"|"escalated"|"dismissed"|"open"}` — no endpoint ever
lets a client set `severity` or `alert_type` after creation, since those
are facts about what triggered the alert, not triage state.

An alert's `status`/`severity` is triage metadata, never a verdict — per
CLAUDE.md, only a `CaseDecision` (§5) is that.

## 4. Cases

| Method | Path | Role |
|---|---|---|
| `GET` | `/cases` | analyst+ |
| `POST` | `/cases` | analyst+ |
| `GET` | `/cases/{id}` | analyst+ |
| `PATCH` | `/cases/{id}` | analyst+ |
| `POST` | `/cases/{id}/decision` | **senior_analyst, admin only** |
| `POST` | `/cases/{id}/evidence` | analyst+ |

`POST /cases` creates a case from one or more `alert_ids` (§5's "attach
multiple alerts to one case" — handled at creation; there is no separate
"add another alert later" endpoint, matching `docs/api-contracts.md`'s
original `POST /cases` contract exactly).

### Status machine

```
open ──────────► investigating ──────────► pending_review
                      │   ▲                       │
                      └───┘                        │
                                                    ▼
                                               resolved ──────► closed
```

`app/services/cases.py::ALLOWED_STATUS_TRANSITIONS`:

| From | May move to |
|---|---|
| `open` | `investigating` |
| `investigating` | `pending_review`, `open` |
| `pending_review` | `investigating`, **not** directly to `resolved` |
| `resolved` | `closed` |
| `closed` | *(terminal)* |

**`resolved` is reachable only through `POST /cases/{id}/decision`,
never through `PATCH /cases/{id}`** — `PATCH` rejects a
`{"status": "resolved"}` body with `422` even from
`investigating`/`pending_review`
(tested: `tests/test_cases_api.py::
test_invalid_status_transition_open_to_resolved_rejected`). This is the
concrete mechanism behind CLAUDE.md's human-in-the-loop rule.

`PATCH /cases/{id}` also handles `priority` and `assigned_analyst_id`
(ordinary PATCH semantics: omit the field to leave it unchanged, send
`null` to unassign; assigning to a nonexistent user id is rejected with
`422`, not silently accepted).

### Decisions

```
POST /cases/{id}/decision
{"decision": "confirmed_fraud"|"not_fraud"|"dismissed", "rationale": "<min 10 chars>"}
```

Restricted to `senior_analyst`/`admin` (`403` for a plain `analyst`,
tested). Requires the case to be `investigating` or `pending_review`
(not `open` — an undirected case shouldn't be resolved sight-unseen).
Creates a `case_decisions` row with `decided_by_user_id` **not null**
(there is no code path that records a decision without an accountable
human) and flips `Case.status` to `resolved` in the same transaction.
Writes an `audit_log_entries` row (`action="case_decision_recorded"`).

**Reading it back**: `GET /cases/{id}/decision` (Phase 7 addition,
`analyst+`) returns the most recent decision, `404` if none has been
recorded yet — added because `POST .../decision`'s response is the
only other place this fact appeared, which doesn't survive a page
reload client-side.

## 5. Evidence

```
POST /cases/{id}/evidence
{"evidence_type": "transaction"|"risk_score"|"shap_explanation"|
   "graph_neighborhood"|"graph_metrics"|"fund_flow"|"historical_stats"|
   "analyst_note",
 "source_id": "<uuid, for every type except analyst_note>",
 "body": "<text, analyst_note only>",
 "hops"/"as_of_step"/"max_hops"/"max_branches": "<optional, graph types>"}
```

Per CLAUDE.md's "no fabrication" rule and this phase's §7, **every
evidence type except `analyst_note` is resolved server-side from a real
record** — the client names *what* to attach (a type + a source id),
never supplies the payload. `app/services/evidence.py` resolves each
type:

| `evidence_type` | `source_id` is | Resolved via |
|---|---|---|
| `transaction` | a transaction id | `app.transactions` row, as-is |
| `risk_score` | a risk_score id | `app.risk_scores` row |
| `shap_explanation` | a risk_score id | that row's stored `shap_values` (`422` if none was computed) |
| `graph_neighborhood` | an account id | `app/services/graph_analytics.py::get_account_neighborhood` — the same code the `/graph/*` API uses |
| `graph_metrics` | an account id | `...::get_account_metrics` |
| `fund_flow` | an account id | `...::get_account_fund_flow` |
| `historical_stats` | an account id | `app/services/history.py::get_sender_history` (requires `as_of_step`) |
| `analyst_note` | — | the request's own `body` — this is the one type that *is* the analyst's statement, not a claim about external data |

**Listing**: `GET /cases/{id}/evidence` (Phase 7 addition, `analyst+`,
paginated) returns what's been attached so far, ordered oldest-first —
added once the frontend needed to show the evidence trail without the
client remembering every id it ever attached.

A `source_id` that doesn't resolve to a real record is rejected with
`404`, never silently accepted or filled with a placeholder. The stored
`source_reference` follows the same `"<table>:<uuid>"` convention
`docs/api-contracts.md` §6.1 already defined for agent-report evidence
citations (`"transaction:<uuid>"`, `"account:<uuid>"`,
`"user:<uuid>"` for a note's author), so this schema is ready to
interoperate with Phase 6's citation format without a second convention.

`evidence_payload` is a point-in-time snapshot (matching
`docs/database-design.md` §4's "no stored aggregate claims anything
about the future") — if the underlying transaction/account/model later
changes, the attached evidence still reflects what was actually observed
at attach time, which is itself part of the audit trail.

## 6. Audit logging

Every login and every case/alert/evidence mutation writes an
`audit_log_entries` row (`app/services/audit.py::record_event`) in the
same database transaction as the action — never a best-effort
side-channel that could silently fail to log a real action, and never
logged for an action that then rolled back.

| `action` | `entity_type` | `user_id` |
|---|---|---|
| `login` | `user` | the logging-in user |
| `risk_score_persisted` | `risk_score` | `null` (service action) |
| `alert_created` | `alert` | `null` (service action) |
| `case_created` | `case` | the creating analyst |
| `case_updated` | `case` | the updating analyst |
| `case_decision_recorded` | `case` | the deciding senior_analyst/admin |
| `evidence_attached` | `case` | the attaching analyst |

`GET /audit-log` — **admin only** — filters by `user_id`, `action`, and
an `occurred_from`/`occurred_to` date range; paginated.

## 7. Known limitations

- **No alert creation from graph-structural rules.** `alerts.alert_type`
  includes `"graph_structural"` and `"manual"` in its `CHECK` constraint
  (so the column can hold them), but nothing in this phase actually
  creates one that way yet — only `POST /risk-scores`'s model-threshold
  path does. Graph-rule-triggered alerts are a reasonable Phase 6+
  addition once there's an agent or scheduled job to run the rule.
- **No pagination cursor stability guarantee** under concurrent writes —
  `limit`/`offset` pagination (same as every other list endpoint in this
  codebase) can skip or repeat a row if new alerts/cases are created
  between pages. Accepted for a local demo at this data volume.
- **Evidence attachment is not itself revocable** — there's no
  `DELETE /cases/{id}/evidence/{id}`; an append-only evidence trail was
  judged more important than editability for a fraud-investigation
  audit record, matching the append-only spirit of `audit_log_entries`.
