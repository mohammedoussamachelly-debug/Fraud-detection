# SentinelAI — Agent Security (Phase 6 Part E)

Status: **implemented and tested** (`backend/tests/test_agent_security.py`,
plus role/permission checks throughout `test_agent_tool_permissions.py`
and `test_investigations_api.py`). This document is the
`security-reviewer` checklist for the investigation agents — read it
alongside `docs/agent-tools.md` (what each tool can reach) and
`docs/multi-agent-architecture.md` (how the workflow is wired).

## 1. No real LLM inference happens in this environment — and nothing
pretends otherwise

Checked before any agent code was written: `ANTHROPIC_API_KEY`,
`OPENAI_API_KEY`, and every other LLM-related env var this project
might plausibly use are **unset** in this environment, in both the
shell and `infra/.env(.example)`. `settings.llm_provider` therefore
defaults to `"mock"`, and `app/agents/llm.py::MockLLMProvider` is the
only provider this environment can actually run — deterministic,
rule-based, zero network calls. Every report it produces is stamped
`model_provider="mock"`, `model_name="mock-deterministic-v1"`,
`is_mock=true`, on the `AgentRun` row and in the report body itself —
there is no code path that silently calls this "real" output. Selecting
`"anthropic"`/`"openai"` without the matching key raises
`LLMProviderUnavailable` immediately, at `POST /cases/{id}/investigations`
time, before an `AgentRun` row is even created
(`tests/test_agent_llm_mock.py::test_get_llm_provider_raises_for_anthropic_without_api_key`)
— a misconfigured deployment fails loudly, it never falls back to mock
and reports the result as if a real model had run.

## 2. Agents cannot modify financial data, scores, or graph records

Every tool in `app/agents/tools.py` is a **read**: `db.get(...)` or a
`select(...)` statement. None contains an `INSERT`/`UPDATE`/`DELETE`.
The only writes this phase's code performs at all are to its own
bookkeeping tables (`agent_runs`, `agent_steps`, `agent_evidence_refs`)
— never to `transactions`, `risk_scores`, `accounts`, or any graph-
derived table. There is no code path, in this phase, by which running
an investigation changes a transaction, a persisted score, or an
account record.

## 3. Agents cannot resolve cases or record human decisions

This is the single most important invariant in this phase, and it's
enforced in three independent places, not just "documented":

1. **`approve_investigation` never touches `Case`.** Finalizing a
   report (`POST /investigations/{run_id}/approve`) sets `AgentRun.
   status="approved"` and copies `draft_report` to `final_report` —
   nothing else. It does not call any function in `app/services/
   cases.py`, does not write a `CaseDecision`, does not change
   `Case.status`. Verified directly:
   `tests/test_agent_security.py::test_investigation_approval_never_creates_a_case_decision`
   asserts zero `CaseDecision` rows and `Case.status == "open"`
   (unchanged) after approving a full investigation.
2. **`record_decision` (Phase 5, unchanged) is still the only function
   that can set `Case.status="resolved"`**, and it requires a human
   `decided_by_user_id` (`NOT NULL`) and a ≥10-character rationale —
   nothing in this phase added a second path to that status.
3. **No agent, tool, or node has a reference to `cases_service.
   record_decision` or `CaseDecision` as a writable target at all** —
   `app/agents/` imports `CaseDecision` exactly once, in
   `get_similar_past_cases`, as a **read-only** query target.

## 4. Treat all retrieved evidence as untrusted input

Per CLAUDE.md's security rule, free text an analyst wrote (a past
case's `CaseDecision.rationale`, surfaced via `get_similar_past_cases`)
is retrieved as **data**, never evaluated, executed, or treated as an
instruction:

- `app/agents/tools.py::get_similar_past_cases` returns it as a plain
  string field in a dict — nothing parses or interprets it.
  (`tests/test_agent_security.py::test_similar_past_case_rationale_is_retrieved_as_plain_data`
  feeds in a prompt-injection-shaped rationale and confirms it comes
  back byte-for-byte as an inert string.)
- `app/agents/prompts.py::build_report_prompt` (used by the real-
  provider path) wraps **every** piece of retrieved evidence/finding/
  feedback text in a labeled `<untrusted_evidence source="..."
  kind="...">...</untrusted_evidence>` tag, with a single up-front
  instruction that tagged content is data, never a command — even if it
  asks the model to change its output format, approve something, or
  ignore prior instructions.
  (`tests/test_agent_security.py::test_build_report_prompt_wraps_evidence_text_as_untrusted_data`.)
- `MockLLMProvider` — the only path that actually runs in this
  environment — never parses evidence/finding summaries as instructions
  at all; it only branches on two booleans it computed itself (`flag`
  values from the tools, never from free text) and copies revision
  `feedback` into `uncertainties` as a quoted excerpt, never as a
  changed decision or action.
  (`tests/test_agent_llm_mock.py::test_mock_provider_quotes_feedback_but_never_executes_it`.)

## 5. Every evidence reference is validated against a real stored record

Covered in depth in `docs/multi-agent-architecture.md` §3 and
`docs/agent-tools.md` §3: tools never fabricate a result for a
nonexistent id (`EvidenceNotFound`), and `report_writer_node` drops any
hypothesis citing a reference that wasn't actually collected in that
run. Both directions are tested
(`tests/test_agent_security.py::test_report_writer_drops_hypothesis_citing_a_fabricated_evidence_ref`,
`...test_report_writer_keeps_hypothesis_citing_a_real_evidence_ref`).

## 6. Traceability: model, prompt, tools, timing, run identity

Every `AgentRun` row records, per Part E's explicit list:

| Field | What it traces |
|---|---|
| `model_provider` / `model_name` | which provider/model actually produced the draft report |
| `prompt_version` (`app/agents/prompts.py::PROMPT_VERSION`) | which instruction text was in effect |
| `tool_versions` (`app/agents/tools.py::TOOL_VERSIONS`) | which version of each tool's query/shape was used |
| `started_at` / `completed_at` (and, per step, on every `AgentStep`) | execution time, down to the individual node attempt |
| `id` (the run id itself) | the unique identifier every API response, audit entry, and evidence reference ties back to |

`agent_steps.tool_calls` records each call's tool name, a short
`args_summary` (stringified arguments — ids and parameters, never a raw
secret or credential; nothing in this system's tool arguments is a
secret in the first place, but the field is structurally incapable of
holding one since it only ever receives `str(value)` of plain ids/
numbers/booleans), a `result_ref` (`"found"`/`"not_found"`, not the
full payload — the full payload lives once in `agent_evidence_refs` or
the step's own `output`, never duplicated per tool call), and a
duration in milliseconds.

## 7. Human approval is structurally required

`app/services/investigations.py` has no code path from `running` to
`approved` — the state machine only reaches `approved` via
`approve_investigation`, called only by
`POST /investigations/{run_id}/approve`, called only by an authenticated
`analyst+` principal (never the `service` principal, which
`start_investigation`'s own route rejects outright —
`tests/test_investigations_api.py::test_start_investigation_rejects_service_credential`).
Every run halts at `awaiting_approval` after the graph finishes; nothing
auto-advances it
(`tests/test_agent_security.py::test_investigation_never_auto_approves`).

## 8. Authorization — who can do what

| Action | Role required |
|---|---|
| Start/view/approve/reject/request-revision an investigation | `analyst`, `senior_analyst`, `admin` |
| Resolve the underlying case (`POST /cases/{id}/decision`) | `senior_analyst`, `admin` **only** — unchanged from Phase 5 |
| Read the audit log | `admin` only |

No request body, query parameter, or header lets a caller choose their
own role — the only role-bearing input anywhere in this system is the
JWT `POST /auth/login` issues, itself derived from `users.role`
(`app/api/deps.py::get_current_user`/`require_role`). This holds for
every route touched by this phase, not just the new ones — see
`docs/authentication.md`'s Phase 6 Part A update for the routes closed
this phase.

## 9. Known limitations

- The real-provider path (`AnthropicLLMProvider`/`OpenAILLMProvider`)
  is implemented but **unverified** — there is no API key in this
  environment to exercise it against a real endpoint. Its prompt-
  injection defenses (§4) are structural (the same delimiting applies
  regardless of provider) but were only exercised through the mock
  path's equivalent checks.
- `get_similar_past_cases`'s simple heuristic (§4 of
  `docs/agent-tools.md`) means a sufficiently different but genuinely
  related past case won't surface — a false negative, not a false
  positive, so it under- rather than over-states similarity.
