"""Read-only evidence tools for the investigation agents (Phase 6 Part B
§6.2 of docs/api-contracts.md). Every function here takes the same `db:
Session` the rest of the backend uses — the `api_service` role, same as
every other route (`app/db/session.py`) — so agents are structurally
incapable of reaching `ground_truth` or acting with elevated privilege;
there is no separate "agent" database credential to misconfigure.

`AGENT_TOOL_PERMISSIONS` + `invoke_tool()` are the explicit allow-list
(Part C "explicit tool permissions", Part E "agents may retrieve
evidence but may not modify..."): each agent name maps to the *only*
tool names it may call, checked at every call, not just at wiring time —
a bug that accidentally imported a wider tool set into a node still
can't actually invoke a tool outside its allow-list.
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Account,
    Alert,
    Case,
    CaseAlert,
    CaseDecision,
    RiskScore,
    Transaction,
)
from app.schemas.transaction import TransactionRead
from app.services import graph_analytics
from app.services.history import get_sender_history


class ToolPermissionError(Exception):
    pass


class EvidenceNotFound(Exception):
    """A requested source id doesn't resolve to a real record — the tool
    returns this rather than fabricating a placeholder result (Part E:
    "validate every evidence reference against actual stored records").
    """


# ---- Evidence Collector tools -------------------------------------------


def get_transaction(db: Session, transaction_id: uuid.UUID) -> dict[str, Any]:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise EvidenceNotFound(f"transaction:{transaction_id}")
    return TransactionRead.model_validate(transaction).model_dump(mode="json")


def get_account_profile(db: Session, account_id: uuid.UUID, as_of_step: int) -> dict[str, Any]:
    account = db.get(Account, account_id)
    if account is None:
        raise EvidenceNotFound(f"account:{account_id}")
    history = get_sender_history(db, account.external_ref, as_of_step)
    return {
        "account_id": str(account_id),
        "external_ref": account.external_ref,
        "account_type": account.account_type,
        "as_of_step": as_of_step,
        **history,
    }


def get_risk_score(db: Session, transaction_id: uuid.UUID) -> dict[str, Any] | None:
    """Latest persisted score for this transaction, or `None` if it was
    never scored — never a fabricated score. No `isFraud`/`isFlaggedFraud`
    field exists on `RiskScore` at all, so there is nothing for this
    function to leak even by accident.
    """
    row = db.scalar(
        select(RiskScore)
        .where(RiskScore.transaction_id == transaction_id)
        .order_by(RiskScore.scored_at.desc())
    )
    if row is None:
        return None
    return {
        "risk_score_id": str(row.id),
        "transaction_id": str(transaction_id),
        "risk_score": float(row.risk_score),
        "risk_level": row.risk_level,
        "model_version": row.model_version,
        "threshold_used": float(row.threshold_used),
        "scored_at": row.scored_at.isoformat(),
    }


def get_shap_explanation(db: Session, transaction_id: uuid.UUID) -> dict[str, Any] | None:
    """The stored SHAP contributions for this transaction's latest score,
    if one was computed with `include_explanation=true`
    (`POST /risk-scores`, Phase 5) — `None` otherwise, never recomputed
    from a possibly-rotated model artifact.
    """
    row = db.scalar(
        select(RiskScore)
        .where(RiskScore.transaction_id == transaction_id)
        .order_by(RiskScore.scored_at.desc())
    )
    if row is None or row.shap_values is None:
        return None
    return {"risk_score_id": str(row.id), "transaction_id": str(transaction_id), **row.shap_values}


def get_similar_past_cases(db: Session, case_id: uuid.UUID) -> list[dict[str, Any]]:
    """Other **resolved** cases that share an account with this case's
    alerted transactions — analyst history (past human decisions), never
    PaySim ground truth (docs/api-contracts.md §6.2). The similarity
    heuristic is deliberately simple (shared account, not a learned
    embedding) and is labeled as exactly that in every result.
    """
    case = db.get(Case, case_id)
    if case is None:
        raise EvidenceNotFound(f"case:{case_id}")

    tx_ids = db.scalars(
        select(Alert.transaction_id)
        .join(CaseAlert, CaseAlert.alert_id == Alert.id)
        .where(CaseAlert.case_id == case_id)
    ).all()
    if not tx_ids:
        return []

    account_ids: set[uuid.UUID] = set()
    for row in db.execute(
        select(Transaction.origin_account_id, Transaction.dest_account_id).where(
            Transaction.id.in_(tx_ids)
        )
    ):
        account_ids.add(row.origin_account_id)
        account_ids.add(row.dest_account_id)
    if not account_ids:
        return []

    other_tx_ids = db.scalars(
        select(Transaction.id).where(
            (Transaction.origin_account_id.in_(account_ids))
            | (Transaction.dest_account_id.in_(account_ids))
        )
    ).all()
    other_case_ids = db.scalars(
        select(CaseAlert.case_id)
        .join(Alert, Alert.id == CaseAlert.alert_id)
        .where(Alert.transaction_id.in_(other_tx_ids), CaseAlert.case_id != case_id)
        .distinct()
    ).all()
    if not other_case_ids:
        return []

    decisions = db.scalars(
        select(CaseDecision)
        .where(CaseDecision.case_id.in_(other_case_ids))
        .order_by(CaseDecision.decided_at.desc())
    ).all()
    return [
        {
            "case_id": str(d.case_id),
            "decision": d.decision,
            "rationale": d.rationale,
            "decided_at": d.decided_at.isoformat(),
            "similarity_basis": (
                "shares a counterparty account with this case's alerted transactions"
            ),
        }
        for d in decisions
    ]


# ---- Network Investigator tools -----------------------------------------


def get_graph_neighborhood(
    db: Session, account_id: uuid.UUID, hops: int, as_of_step: int | None
) -> dict[str, Any]:
    try:
        result = graph_analytics.get_account_neighborhood(
            db, account_id, hops=hops, as_of_step=as_of_step
        )
    except graph_analytics.AccountNotFound as exc:
        raise EvidenceNotFound(f"account:{account_id}") from exc
    return result.model_dump(mode="json")


def get_graph_metrics(db: Session, account_id: uuid.UUID, as_of_step: int | None) -> dict[str, Any]:
    try:
        result = graph_analytics.get_account_metrics(db, account_id, as_of_step=as_of_step)
    except graph_analytics.AccountNotFound as exc:
        raise EvidenceNotFound(f"account:{account_id}") from exc
    return result.model_dump(mode="json")


def get_fund_flow(
    db: Session,
    account_id: uuid.UUID,
    as_of_step: int | None,
    max_hops: int,
    max_branches: int,
) -> dict[str, Any]:
    try:
        result = graph_analytics.get_account_fund_flow(
            db, account_id, as_of_step=as_of_step, max_hops=max_hops, max_branches=max_branches
        )
    except graph_analytics.AccountNotFound as exc:
        raise EvidenceNotFound(f"account:{account_id}") from exc
    return result.model_dump(mode="json")


# ---- Permission registry -------------------------------------------------

TOOL_REGISTRY: dict[str, Callable[..., Any]] = {
    "get_transaction": get_transaction,
    "get_account_profile": get_account_profile,
    "get_risk_score": get_risk_score,
    "get_shap_explanation": get_shap_explanation,
    "get_similar_past_cases": get_similar_past_cases,
    "get_graph_neighborhood": get_graph_neighborhood,
    "get_graph_metrics": get_graph_metrics,
    "get_fund_flow": get_fund_flow,
}

AGENT_TOOL_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "evidence_collector": (
        "get_transaction",
        "get_account_profile",
        "get_risk_score",
        "get_shap_explanation",
        "get_similar_past_cases",
    ),
    "network_investigator": ("get_graph_neighborhood", "get_graph_metrics", "get_fund_flow"),
    # report_writer gets no tools at all — it only ever sees state already
    # collected and persisted by the two agents above (Part C "explicit
    # tool permissions"; Part E "agents may retrieve evidence but may not
    # modify" — report_writer doesn't even retrieve).
    "report_writer": (),
}

# Recorded on every `AgentRun.tool_versions` (Part E: "record ... tool
# versions"). Bumped whenever a tool function's query/shape changes.
TOOL_VERSIONS = {name: "v1" for name in TOOL_REGISTRY}


def invoke_tool(agent_name: str, tool_name: str, db: Session, **kwargs: Any) -> Any:
    allowed = AGENT_TOOL_PERMISSIONS.get(agent_name, ())
    if tool_name not in allowed:
        raise ToolPermissionError(f"{agent_name!r} is not permitted to call tool {tool_name!r}")
    return TOOL_REGISTRY[tool_name](db, **kwargs)
