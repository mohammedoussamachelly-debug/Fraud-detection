"""Orchestrates one investigation run end to end: builds and invokes the
LangGraph workflow (Part C), persists `AgentRun`/`AgentStep`/
`AgentEvidenceRef` rows as it goes (Part D), and exposes the
approve/reject/request-revision human-review actions (Part F).

**Why no LangGraph checkpointer**: docs/architecture.md §7.2 already
commits to "workflow state is persisted in Postgres so a run survives a
backend restart" — that's `AgentRun`/`AgentStep` here, not LangGraph's
own checkpoint store. A `request-revision` round trip is therefore
implemented as a *fresh* graph invocation starting at `report_writer`
with the evidence/findings already on file (read back from
`AgentEvidenceRef`) plus the new feedback, never a live `interrupt()`/
resume of a suspended coroutine — simpler, needs no extra persistence
layer or Postgres checkpointer package, and satisfies Part C's "do not
create unnecessary autonomous loops" by construction (each revision is
one bounded, auditable re-run, not an open-ended loop).

**Why a background thread, not a task queue**: CLAUDE.md's approved
stack has no message queue ("deliberately a modular monolith"). A
`ThreadPoolExecutor` submission is enough to make
`POST /cases/{id}/investigations` return immediately
(Part F: "should not block ordinary API requests indefinitely") without
adding infrastructure the project doesn't otherwise use. The tradeoff —
an in-flight run is not auto-resumed if the process restarts mid-run —
is a documented limitation (`docs/multi-agent-architecture.md`), not a
silent gap: the run's `AgentStep` history up to that point is never
lost, only its *continuation*.
"""

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, datetime

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.graph import (
    evidence_collector_node,
    intake_node,
    network_investigator_node,
    report_writer_node,
)
from app.agents.llm import LLMProvider, get_llm_provider
from app.agents.state import EvidenceItem, InvestigationState, NetworkFinding
from app.agents.tools import AGENT_TOOL_PERMISSIONS, TOOL_VERSIONS
from app.core.config import Settings, get_settings
from app.db.models import AgentEvidenceRef, AgentRun, AgentStep, Case
from app.db.models.agent_run import MAX_REVISION_ROUNDS
from app.db.session import SessionLocal
from app.services import audit

logger = logging.getLogger("sentinelai.agents")

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="investigation")
# Separate pool for the per-node wall-clock bound (`_run_node_logic`) —
# kept distinct from `_EXECUTOR` (which backgrounds whole runs) so a
# timed-out node attempt occupying a worker here can never starve a
# different run's top-level execution.
_TIMEOUT_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="investigation-node")
_MAX_NODE_ATTEMPTS = 3


class CaseNotFound(Exception):
    pass


class RunNotFound(Exception):
    pass


class InvalidRunTransition(Exception):
    pass


class RevisionLimitExceeded(Exception):
    pass


def start_investigation(db: Session, case_id: uuid.UUID, actor_user_id: uuid.UUID) -> AgentRun:
    """Creates the `AgentRun` row (status=`running`) and submits the
    actual graph execution to the background executor, returning
    immediately — the API route never blocks on agent/LLM work.
    """
    case = db.get(Case, case_id)
    if case is None:
        raise CaseNotFound(str(case_id))

    settings = get_settings()
    provider = get_llm_provider(settings)  # fails fast if misconfigured, before the run is created

    run = AgentRun(
        case_id=case_id,
        started_by_user_id=actor_user_id,
        status="running",
        model_provider=provider.model_provider,
        model_name=provider.model_name,
        prompt_version=_prompt_version(),
        tool_versions=dict(TOOL_VERSIONS),
    )
    db.add(run)
    audit.record_event(
        db,
        user_id=actor_user_id,
        action="investigation_started",
        entity_type="case",
        entity_id=case_id,
        metadata={"agent_run_id": str(run.id)},
    )
    db.commit()

    _EXECUTOR.submit(_execute_run, run.id)
    return run


def _prompt_version() -> str:
    from app.agents.prompts import PROMPT_VERSION

    return PROMPT_VERSION


def _execute_run(run_id: uuid.UUID) -> None:
    """Runs in a background thread with its own DB session — never the
    request-scoped session, which closes as soon as the HTTP response
    for `POST /cases/{id}/investigations` is sent.
    """
    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        if run is None:
            logger.error("agent run %s vanished before execution", run_id)
            return

        settings = get_settings()
        provider = get_llm_provider(settings)
        graph = _build_graph(db, run_id, provider, settings)

        try:
            result = graph.invoke({"run_id": str(run_id), "case_id": str(run.case_id)})
        except Exception as exc:  # noqa: BLE001  (top-level run failure boundary, by design)
            logger.exception("investigation run %s failed", run_id)
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = datetime.now(UTC)
            db.commit()
            return

        run.status = "awaiting_approval"
        run.draft_report = result.get("report")
        db.commit()

        _persist_evidence_refs(db, run_id, result)
    finally:
        db.close()


def _persist_evidence_refs(db: Session, run_id: uuid.UUID, result: dict) -> None:
    for item in result.get("evidence", []):
        db.add(
            AgentEvidenceRef(
                agent_run_id=run_id,
                evidence_type=item["evidence_type"],
                source_reference=item["source_reference"],
                summary=item["summary"],
                collected_by_node="evidence_collector",
            )
        )
    for item in result.get("network_findings", []):
        db.add(
            AgentEvidenceRef(
                agent_run_id=run_id,
                evidence_type="network_finding",
                source_reference=item["source_reference"],
                summary=item["summary"],
                collected_by_node="network_investigator",
            )
        )
    db.commit()


def _record_step(
    db: Session,
    run_id: uuid.UUID,
    node_name: str,
    status: str,
    tool_calls: list[dict],
    output: dict | None,
    error: str | None,
    started_at: datetime,
) -> None:
    attempt = (
        db.scalar(
            select(func.count())
            .select_from(AgentStep)
            .where(AgentStep.agent_run_id == run_id, AgentStep.node_name == node_name)
        )
        or 0
    ) + 1
    db.add(
        AgentStep(
            agent_run_id=run_id,
            node_name=node_name,
            attempt=attempt,
            status=status,
            tool_calls=tool_calls,
            output=output,
            error=error,
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )
    )
    db.commit()


def _run_node_logic(
    node_name: str, provider: LLMProvider, state: InvestigationState
) -> tuple[dict, list[dict]]:
    """The actual node work, run inside `_TIMEOUT_EXECUTOR` on its *own*
    dedicated DB session — never the run-level session the calling
    thread uses for step-recording. If `future.result(timeout=...)`
    below times out, this function may still be running in its worker
    thread (Python cannot preemptively cancel a blocking call); giving
    it its own session means that abandoned work can never corrupt or
    race against the session the orchestrator keeps using.
    """
    tool_log: list[dict] = []
    if node_name == "report_writer":
        return report_writer_node(provider, state), tool_log

    node_db = SessionLocal()
    try:
        if node_name == "intake":
            return intake_node(node_db, state), tool_log
        if node_name == "evidence_collector":
            return evidence_collector_node(node_db, state, tool_log), tool_log
        if node_name == "network_investigator":
            return network_investigator_node(node_db, state, tool_log), tool_log
        return {"status": "awaiting_approval"}, tool_log  # human_approval_gate
    finally:
        node_db.close()


def _build_graph(db: Session, run_id: uuid.UUID, provider: LLMProvider, settings: Settings):
    def _wrap(node_name: str):
        def wrapped(state: InvestigationState) -> dict:
            started_at = datetime.now(UTC)
            future = _TIMEOUT_EXECUTOR.submit(_run_node_logic, node_name, provider, state)
            try:
                out, tool_log = future.result(timeout=settings.agent_node_timeout_seconds)
            except FuturesTimeoutError as exc:
                _record_step(
                    db,
                    run_id,
                    node_name,
                    "failed",
                    [],
                    None,
                    f"node timed out after {settings.agent_node_timeout_seconds}s",
                    started_at,
                )
                raise TimeoutError(f"{node_name} exceeded its node timeout") from exc
            except Exception as exc:
                _record_step(db, run_id, node_name, "failed", [], None, str(exc), started_at)
                raise
            _record_step(
                db, run_id, node_name, "succeeded", tool_log, _safe_output(out), None, started_at
            )
            return out

        return wrapped

    builder = StateGraph(InvestigationState)
    # LangGraph's native per-node `timeout=` is async-only in the
    # installed version (1.2.20) — raises `ValueError` at `.compile()`
    # time for the sync nodes this graph uses throughout, discovered
    # while smoke-testing this exact pipeline. `retry_policy` has no such
    # restriction, so it's still the official interface for bounded
    # retries; the wall-clock bound above is our own
    # `ThreadPoolExecutor.submit().result(timeout=...)`, applied inside
    # every node regardless of LangGraph version.
    retry = RetryPolicy(max_attempts=_MAX_NODE_ATTEMPTS, retry_on=Exception)

    builder.add_node("intake", _wrap("intake"), retry_policy=retry)
    builder.add_node("evidence_collector", _wrap("evidence_collector"), retry_policy=retry)
    builder.add_node("network_investigator", _wrap("network_investigator"), retry_policy=retry)
    builder.add_node("report_writer", _wrap("report_writer"), retry_policy=retry)
    builder.add_node("human_approval_gate", _wrap("human_approval_gate"))

    builder.add_edge(START, "intake")
    builder.add_edge("intake", "evidence_collector")
    builder.add_edge("evidence_collector", "network_investigator")
    builder.add_edge("network_investigator", "report_writer")
    builder.add_edge("report_writer", "human_approval_gate")
    builder.add_edge("human_approval_gate", END)

    return builder.compile()


def _safe_output(out: dict) -> dict:
    """Output persisted to `agent_steps.output` — Part D: "avoid storing
    unnecessary sensitive data... in model traces". Nothing in this
    system handles secrets/PII, but this still caps size and drops the
    full `report` object (already stored once on `agent_runs.draft_report`,
    no need to duplicate it in every step row).
    """
    return {k: v for k, v in out.items() if k not in ("report",)}


def get_investigation(db: Session, run_id: uuid.UUID) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise RunNotFound(str(run_id))
    return run


def list_steps(db: Session, run_id: uuid.UUID) -> list[AgentStep]:
    return list(
        db.scalars(
            select(AgentStep).where(AgentStep.agent_run_id == run_id).order_by(AgentStep.started_at)
        ).all()
    )


def list_evidence_refs(db: Session, run_id: uuid.UUID) -> list[AgentEvidenceRef]:
    return list(
        db.scalars(
            select(AgentEvidenceRef)
            .where(AgentEvidenceRef.agent_run_id == run_id)
            .order_by(AgentEvidenceRef.created_at)
        ).all()
    )


def list_runs_for_case(
    db: Session, case_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[AgentRun], int]:
    """Run history for a case's "Investigations" tab — summaries only; a
    caller wanting one run's steps/evidence/report still goes to
    `GET /investigations/{run_id}` (`get_investigation`/`list_steps`/
    `list_evidence_refs` above).
    """
    if db.get(Case, case_id) is None:
        raise CaseNotFound(str(case_id))

    stmt = select(AgentRun).where(AgentRun.case_id == case_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(stmt.order_by(AgentRun.started_at.desc()).limit(limit).offset(offset)).all()
    )
    return rows, total


def approve_investigation(db: Session, run_id: uuid.UUID, actor_user_id: uuid.UUID) -> AgentRun:
    """Finalizes the draft as the case's investigation record. This is
    **not** a case decision — it never touches `Case.status` or creates
    a `CaseDecision` row (Part E: "agents cannot resolve cases... require
    an authorized human for consequential case decisions" — approving a
    *report* and deciding a *case* are deliberately two separate actions,
    the latter still only via `POST /cases/{id}/decision`).
    """
    run = _require_run(db, run_id)
    if run.status == "approved":
        return run  # idempotent: approving twice is a no-op, not an error
    if run.status != "awaiting_approval":
        raise InvalidRunTransition(f"{run.status} -> approved")

    run.status = "approved"
    run.final_report = run.draft_report
    run.completed_at = datetime.now(UTC)
    audit.record_event(
        db,
        user_id=actor_user_id,
        action="investigation_approved",
        entity_type="case",
        entity_id=run.case_id,
        metadata={"agent_run_id": str(run.id)},
    )
    db.commit()
    return run


def reject_investigation(db: Session, run_id: uuid.UUID, actor_user_id: uuid.UUID) -> AgentRun:
    run = _require_run(db, run_id)
    if run.status == "rejected":
        return run
    if run.status != "awaiting_approval":
        raise InvalidRunTransition(f"{run.status} -> rejected")

    run.status = "rejected"
    run.completed_at = datetime.now(UTC)
    audit.record_event(
        db,
        user_id=actor_user_id,
        action="investigation_rejected",
        entity_type="case",
        entity_id=run.case_id,
        metadata={"agent_run_id": str(run.id)},
    )
    db.commit()
    return run


def request_revision(
    db: Session, run_id: uuid.UUID, actor_user_id: uuid.UUID, feedback: str
) -> AgentRun:
    """Re-runs only the `report_writer` node — evidence/network findings
    already on file (`AgentEvidenceRef`) are reused, never re-collected,
    so a revision round trip costs one LLM call, not a full re-investigation.
    Bounded at `MAX_REVISION_ROUNDS` (Part C: no unbounded loop).
    """
    run = _require_run(db, run_id)
    if run.status != "awaiting_approval":
        raise InvalidRunTransition(f"{run.status} -> revision_requested")
    if run.revision_count >= MAX_REVISION_ROUNDS:
        raise RevisionLimitExceeded(
            f"run {run_id} has already used {MAX_REVISION_ROUNDS} revisions"
        )

    settings = get_settings()
    provider = get_llm_provider(settings)

    evidence_refs = list_evidence_refs(db, run_id)
    evidence: list[EvidenceItem] = [
        EvidenceItem(
            evidence_type=r.evidence_type,
            source_reference=r.source_reference,
            summary=r.summary,
            flag=False,
            payload={},
        )
        for r in evidence_refs
        if r.collected_by_node == "evidence_collector"
    ]
    network_findings: list[NetworkFinding] = [
        NetworkFinding(
            evidence_type=r.evidence_type,
            source_reference=r.source_reference,
            summary=r.summary,
            flag=False,
            payload={},
        )
        for r in evidence_refs
        if r.collected_by_node == "network_investigator"
    ]
    feedback_history = [*run.review_feedback, feedback]

    started_at = datetime.now(UTC)
    state: InvestigationState = {
        "case_id": str(run.case_id),
        "evidence": evidence,
        "network_findings": network_findings,
        "feedback": feedback_history,
    }
    try:
        out = report_writer_node(provider, state)
    except Exception as exc:
        _record_step(db, run_id, "report_writer", "failed", [], None, str(exc), started_at)
        raise
    _record_step(db, run_id, "report_writer", "succeeded", [], _safe_output(out), None, started_at)

    run.review_feedback = feedback_history
    run.revision_count = run.revision_count + 1
    run.draft_report = out["report"]
    run.status = "awaiting_approval"
    audit.record_event(
        db,
        user_id=actor_user_id,
        action="investigation_revision_requested",
        entity_type="case",
        entity_id=run.case_id,
        metadata={"agent_run_id": str(run.id), "revision_count": run.revision_count},
    )
    db.commit()
    return run


def _require_run(db: Session, run_id: uuid.UUID) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise RunNotFound(str(run_id))
    return run


__all__ = [
    "AGENT_TOOL_PERMISSIONS",
    "CaseNotFound",
    "InvalidRunTransition",
    "RevisionLimitExceeded",
    "RunNotFound",
    "approve_investigation",
    "get_investigation",
    "list_evidence_refs",
    "list_steps",
    "reject_investigation",
    "request_revision",
    "start_investigation",
]
