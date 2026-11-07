"""Node logic for the three investigation agents (Part B). Each function
here is pure with respect to persistence — it takes a `db` session (the
same `api_service`-scoped session as the rest of the backend) and the
current `InvestigationState`, and returns only the state keys it adds or
changes. LangGraph wiring (nodes, edges, retries, timeouts) and durable
persistence (`AgentRun`/`AgentStep`/`AgentEvidenceRef`) both live in
`app/services/investigations.py` — mirroring this codebase's existing
split between `app/graph/` (pure algorithms) and
`app/services/graph_analytics.py` (DB-aware orchestration).

Agent 3 (`report_writer_node`) calls no tool at all — Part C's "explicit
tool permissions" (`app/agents/tools.py::AGENT_TOOL_PERMISSIONS`) grants
it an empty allow-list; it only ever sees what Agents 1 and 2 already
collected and validated.
"""

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.llm import LLMProvider, ReportInputs
from app.agents.state import InvestigationState
from app.agents.tools import EvidenceNotFound, invoke_tool
from app.db.models import Alert, Case, CaseAlert, Transaction

# Model-score threshold above which an evidence item is "flagged" for the
# report writer's attention — same semantics as `app/ml/inference.py`'s
# "high" band, re-derived here rather than imported to keep this module
# free of a dependency on the ML inference module (it never scores
# anything itself, only reads already-persisted scores).
_FLAG_RISK_LEVELS = {"high"}


class IntakeError(Exception):
    pass


def intake_node(db: Session, state: InvestigationState) -> dict[str, Any]:
    """Loads the case and every transaction/account its alerts touch.
    This is case bookkeeping, not an evidence *tool* call — it doesn't go
    through `invoke_tool`/the permission registry, matching
    docs/architecture.md §7.1's Intake step ("load the case, the
    triggering alert, and the account(s) involved").
    """
    case_id = uuid.UUID(state["case_id"])
    case = db.get(Case, case_id)
    if case is None:
        raise IntakeError(f"case not found: {case_id}")

    transaction_ids = db.scalars(
        select(Alert.transaction_id)
        .join(CaseAlert, CaseAlert.alert_id == Alert.id)
        .where(CaseAlert.case_id == case_id)
    ).all()
    if not transaction_ids:
        raise IntakeError(f"case {case_id} has no linked alerts/transactions to investigate")

    account_ids: set[uuid.UUID] = set()
    for row in db.execute(
        select(Transaction.origin_account_id, Transaction.dest_account_id).where(
            Transaction.id.in_(transaction_ids)
        )
    ):
        account_ids.add(row.origin_account_id)
        account_ids.add(row.dest_account_id)

    return {
        "transaction_ids": [str(t) for t in transaction_ids],
        "account_ids": [str(a) for a in account_ids],
        "status": "running",
    }


def evidence_collector_node(
    db: Session, state: InvestigationState, tool_log: list[dict]
) -> dict[str, Any]:
    """Agent 1. Retrieves case/transaction/risk-score/SHAP/similar-case
    evidence through the `evidence_collector` tool allow-list only.
    """
    evidence: list[dict] = []
    max_step = 0

    for tx_id_str in state["transaction_ids"]:
        tx_id = uuid.UUID(tx_id_str)
        try:
            tx = _call(tool_log, "evidence_collector", "get_transaction", db, transaction_id=tx_id)
        except EvidenceNotFound:
            continue
        max_step = max(max_step, tx["step"])
        evidence.append(
            {
                "evidence_type": "transaction",
                "source_reference": f"transaction:{tx_id}",
                "summary": (
                    f"{tx['type']} of {tx['amount']} at step {tx['step']} "
                    f"({tx['origin_account_id']} -> {tx['dest_account_id']})"
                ),
                "flag": False,
                "payload": tx,
            }
        )

        risk = _call(tool_log, "evidence_collector", "get_risk_score", db, transaction_id=tx_id)
        if risk is not None:
            evidence.append(
                {
                    "evidence_type": "risk_score",
                    "source_reference": f"risk_score:{risk['risk_score_id']}",
                    "summary": (
                        f"Model {risk['model_version']} scored this transaction "
                        f"{risk['risk_score']:.4f} ({risk['risk_level']}, threshold "
                        f"{risk['threshold_used']:.4f})"
                    ),
                    "flag": risk["risk_level"] in _FLAG_RISK_LEVELS,
                    "payload": risk,
                }
            )

            shap = _call(
                tool_log, "evidence_collector", "get_shap_explanation", db, transaction_id=tx_id
            )
            if shap is not None:
                evidence.append(
                    {
                        "evidence_type": "shap_explanation",
                        "source_reference": f"risk_score:{shap['risk_score_id']}",
                        "summary": "SHAP feature contributions recorded at scoring time",
                        "flag": False,
                        "payload": shap,
                    }
                )

    for account_id_str in state["account_ids"]:
        account_id = uuid.UUID(account_id_str)
        # `get_sender_history` filters strictly `step < as_of_step`
        # (app/services/history.py) — passing `max_step` here, not
        # `max_step + 1`, is what excludes the case's own investigated
        # transaction(s) from counting as their own "prior" history.
        # Found and fixed while smoke-testing this exact pipeline: the
        # `+ 1` version let a transaction's own step-5 event count
        # itself as 1 prior transaction, a leakage bug CLAUDE.md
        # explicitly rules out.
        profile = _call(
            tool_log,
            "evidence_collector",
            "get_account_profile",
            db,
            account_id=account_id,
            as_of_step=max_step,
        )
        evidence.append(
            {
                "evidence_type": "historical_stats",
                "source_reference": f"account:{account_id}",
                "summary": (
                    f"Account {profile['external_ref']}: "
                    f"{profile['num_prev_txns_by_sender']} prior txns, "
                    f"{profile['num_unique_prev_recipients']} unique recipients"
                ),
                "flag": False,
                "payload": profile,
            }
        )

    similar = _call(
        tool_log,
        "evidence_collector",
        "get_similar_past_cases",
        db,
        case_id=uuid.UUID(state["case_id"]),
    )
    for s in similar:
        # The rationale is the analyst's own free text — genuine
        # evidentiary value (Part B: "retrieve relevant previous
        # investigation findings"), but untrusted input per CLAUDE.md:
        # `app/agents/prompts.py::build_report_prompt` wraps every
        # evidence summary (this one included) in a labeled
        # `<untrusted_evidence>` tag before it ever reaches a real LLM
        # prompt, and the mock provider never parses summaries as
        # instructions at all — see tests/test_agent_security.py.
        rationale_excerpt = s["rationale"][:200]
        evidence.append(
            {
                "evidence_type": "similar_case",
                "source_reference": f"case:{s['case_id']}",
                "summary": (
                    f"Case {s['case_id']} was resolved as {s['decision']}: {rationale_excerpt}"
                ),
                "flag": s["decision"] == "confirmed_fraud",
                "payload": s,
            }
        )

    return {"evidence": evidence}


def network_investigator_node(
    db: Session, state: InvestigationState, tool_log: list[dict]
) -> dict[str, Any]:
    """Agent 2. Calls only the `network_investigator` tool allow-list
    (the existing, already-tested `app/graph/`/`app/services/
    graph_analytics.py` NetworkX functions) — never writes, never scores.
    """
    findings: list[dict] = []

    for account_id_str in state["account_ids"]:
        account_id = uuid.UUID(account_id_str)

        metrics = _call(
            tool_log,
            "network_investigator",
            "get_graph_metrics",
            db,
            account_id=account_id,
            as_of_step=None,
        )
        fan = metrics["fan_in_pattern"] or metrics["fan_out_pattern"]
        findings.append(
            {
                "evidence_type": "network_finding",
                "source_reference": f"account:{account_id}",
                "summary": (
                    f"Account has {metrics['incoming_transaction_count']} incoming / "
                    f"{metrics['outgoing_transaction_count']} outgoing txns "
                    f"(fan_in={metrics['fan_in_pattern']}, fan_out={metrics['fan_out_pattern']})"
                ),
                "flag": fan,
                "payload": metrics,
            }
        )

        neighborhood = _call(
            tool_log,
            "network_investigator",
            "get_graph_neighborhood",
            db,
            account_id=account_id,
            hops=2,
            as_of_step=None,
        )
        if neighborhood["cycles"]:
            findings.append(
                {
                    "evidence_type": "network_finding",
                    "source_reference": f"account:{account_id}",
                    "summary": (
                        f"{len(neighborhood['cycles'])} cycle(s) detected in 2-hop neighborhood"
                    ),
                    "flag": True,
                    "payload": {"cycles": neighborhood["cycles"]},
                }
            )

    return {"network_findings": findings}


def report_writer_node(llm_provider: LLMProvider, state: InvestigationState) -> dict[str, Any]:
    """Agent 3. No DB session, no tool access at all — operates only on
    evidence/findings Agents 1 and 2 already collected and validated.
    Drops any hypothesis citing an evidence_ref that wasn't actually
    collected (Part E: "validate every evidence reference against actual
    stored records").
    """
    evidence = state.get("evidence", [])
    network_findings = state.get("network_findings", [])
    inputs = ReportInputs(
        case_summary={"case_id": state["case_id"]},
        evidence=evidence,
        network_findings=network_findings,
        feedback=state.get("feedback", []),
    )
    generated = llm_provider.generate_report(inputs)

    valid_refs = {e["source_reference"] for e in evidence} | {
        f["source_reference"] for f in network_findings
    }
    hypotheses = [
        h
        for h in generated.hypotheses
        if h.get("evidence_refs") and all(ref in valid_refs for ref in h["evidence_refs"])
    ]
    dropped = len(generated.hypotheses) - len(hypotheses)
    uncertainties = list(generated.uncertainties)
    if dropped:
        uncertainties.append(
            f"{dropped} hypothesis/es were dropped: they cited an evidence reference not "
            "found among the evidence actually retrieved for this run."
        )

    report = {
        "summary": generated.summary,
        "hypotheses": hypotheses,
        "uncertainties": uncertainties,
        "recommended_next_step": generated.recommended_next_step,
        "model_provider": generated.model_provider,
        "model_name": generated.model_name,
        "is_mock": generated.is_mock,
        "evidence_refs": sorted(valid_refs),
    }
    return {"report": report, "status": "awaiting_approval"}


def _call(tool_log: list[dict], agent_name: str, tool_name: str, db: Session, **kwargs: Any) -> Any:
    start = time.perf_counter()
    args_summary = {k: str(v) for k, v in kwargs.items()}
    try:
        result = invoke_tool(agent_name, tool_name, db, **kwargs)
    except EvidenceNotFound as exc:
        tool_log.append(
            {
                "tool": tool_name,
                "args_summary": args_summary,
                "result_ref": None,
                "error": str(exc),
                "duration_ms": round((time.perf_counter() - start) * 1000, 2),
            }
        )
        raise
    tool_log.append(
        {
            "tool": tool_name,
            "args_summary": args_summary,
            "result_ref": "found" if result is not None else "not_found",
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }
    )
    return result
