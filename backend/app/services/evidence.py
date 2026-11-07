"""Resolves and attaches case evidence. Per §7 of the Phase 5 brief and
CLAUDE.md's "no fabrication" rule: every evidence type except
`analyst_note` is computed here, server-side, from a real source record —
the client names *what* to attach (a type + a source id), never supplies
the payload itself. If the source id doesn't resolve to a real record,
attaching fails; nothing is ever synthesized to fill the gap.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Account, Case, CaseEvidence, RiskScore, Transaction
from app.schemas.case_evidence import CaseEvidenceAttachRequest, CaseEvidenceRead
from app.schemas.transaction import TransactionRead
from app.services import audit, graph_analytics
from app.services.history import get_sender_history


class CaseNotFound(Exception):
    pass


class SourceRecordNotFound(Exception):
    pass


class InvalidEvidenceRequest(Exception):
    pass


def _resolve_transaction(db: Session, source_id: uuid.UUID | None) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest("source_id is required for evidence_type=transaction")
    transaction = db.get(Transaction, source_id)
    if transaction is None:
        raise SourceRecordNotFound(f"transaction:{source_id}")
    return f"transaction:{transaction.id}", TransactionRead.model_validate(transaction).model_dump(
        mode="json"
    )


def _resolve_risk_score(db: Session, source_id: uuid.UUID | None) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest("source_id is required for evidence_type=risk_score")
    risk_score = db.get(RiskScore, source_id)
    if risk_score is None:
        raise SourceRecordNotFound(f"risk_score:{source_id}")
    payload = {
        "transaction_id": str(risk_score.transaction_id),
        "risk_score": float(risk_score.risk_score),
        "risk_level": risk_score.risk_level,
        "model_version": risk_score.model_version,
        "threshold_used": float(risk_score.threshold_used),
        "scored_at": risk_score.scored_at.isoformat(),
    }
    return f"risk_score:{risk_score.id}", payload


def _resolve_shap_explanation(db: Session, source_id: uuid.UUID | None) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest("source_id is required for evidence_type=shap_explanation")
    risk_score = db.get(RiskScore, source_id)
    if risk_score is None:
        raise SourceRecordNotFound(f"risk_score:{source_id}")
    if risk_score.shap_values is None:
        raise InvalidEvidenceRequest(
            "this risk score has no SHAP explanation; it must be re-scored with "
            "include_explanation=true before it can be attached as evidence"
        )
    return f"risk_score:{risk_score.id}", risk_score.shap_values


def _resolve_graph_neighborhood(
    db: Session, source_id: uuid.UUID | None, hops: int | None, as_of_step: int | None
) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest(
            "source_id (account id) is required for evidence_type=graph_neighborhood"
        )
    try:
        result = graph_analytics.get_account_neighborhood(
            db, source_id, hops=hops or 2, as_of_step=as_of_step
        )
    except graph_analytics.AccountNotFound as exc:
        raise SourceRecordNotFound(f"account:{source_id}") from exc
    return f"account:{source_id}", result.model_dump(mode="json")


def _resolve_graph_metrics(
    db: Session, source_id: uuid.UUID | None, as_of_step: int | None
) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest(
            "source_id (account id) is required for evidence_type=graph_metrics"
        )
    try:
        result = graph_analytics.get_account_metrics(db, source_id, as_of_step=as_of_step)
    except graph_analytics.AccountNotFound as exc:
        raise SourceRecordNotFound(f"account:{source_id}") from exc
    return f"account:{source_id}", result.model_dump(mode="json")


def _resolve_fund_flow(
    db: Session,
    source_id: uuid.UUID | None,
    as_of_step: int | None,
    max_hops: int | None,
    max_branches: int | None,
) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest(
            "source_id (account id) is required for evidence_type=fund_flow"
        )
    try:
        result = graph_analytics.get_account_fund_flow(
            db,
            source_id,
            as_of_step=as_of_step,
            max_hops=max_hops or 3,
            max_branches=max_branches or 3,
        )
    except graph_analytics.AccountNotFound as exc:
        raise SourceRecordNotFound(f"account:{source_id}") from exc
    return f"account:{source_id}", result.model_dump(mode="json")


def _resolve_historical_stats(
    db: Session, source_id: uuid.UUID | None, as_of_step: int | None
) -> tuple[str, dict]:
    if source_id is None:
        raise InvalidEvidenceRequest(
            "source_id (account id) is required for evidence_type=historical_stats"
        )
    if as_of_step is None:
        raise InvalidEvidenceRequest("as_of_step is required for evidence_type=historical_stats")
    account = db.get(Account, source_id)
    if account is None:
        raise SourceRecordNotFound(f"account:{source_id}")
    history = get_sender_history(db, account.external_ref, as_of_step)
    return f"account:{source_id}", {"as_of_step": as_of_step, **history}


def _resolve_analyst_note(body: str | None, actor_user_id: uuid.UUID) -> tuple[str, dict]:
    if not body:
        raise InvalidEvidenceRequest("body is required for evidence_type=analyst_note")
    return f"user:{actor_user_id}", {"body": body}


def attach_evidence(
    db: Session, case_id: uuid.UUID, request: CaseEvidenceAttachRequest, actor_user_id: uuid.UUID
) -> CaseEvidenceRead:
    case = db.get(Case, case_id)
    if case is None:
        raise CaseNotFound(str(case_id))

    if request.evidence_type == "transaction":
        source_reference, payload = _resolve_transaction(db, request.source_id)
    elif request.evidence_type == "risk_score":
        source_reference, payload = _resolve_risk_score(db, request.source_id)
    elif request.evidence_type == "shap_explanation":
        source_reference, payload = _resolve_shap_explanation(db, request.source_id)
    elif request.evidence_type == "graph_neighborhood":
        source_reference, payload = _resolve_graph_neighborhood(
            db, request.source_id, request.hops, request.as_of_step
        )
    elif request.evidence_type == "graph_metrics":
        source_reference, payload = _resolve_graph_metrics(
            db, request.source_id, request.as_of_step
        )
    elif request.evidence_type == "fund_flow":
        source_reference, payload = _resolve_fund_flow(
            db, request.source_id, request.as_of_step, request.max_hops, request.max_branches
        )
    elif request.evidence_type == "historical_stats":
        source_reference, payload = _resolve_historical_stats(
            db, request.source_id, request.as_of_step
        )
    else:  # "analyst_note"
        source_reference, payload = _resolve_analyst_note(request.body, actor_user_id)

    evidence = CaseEvidence(
        case_id=case_id,
        evidence_type=request.evidence_type,
        source_reference=source_reference,
        evidence_payload=payload,
    )
    db.add(evidence)
    db.flush()

    audit.record_event(
        db,
        user_id=actor_user_id,
        action="evidence_attached",
        entity_type="case",
        entity_id=case_id,
        metadata={"evidence_id": str(evidence.id), "evidence_type": request.evidence_type},
    )
    db.commit()
    return CaseEvidenceRead.model_validate(evidence)


def list_evidence_for_case(
    db: Session, case_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[CaseEvidence], int]:
    if db.get(Case, case_id) is None:
        raise CaseNotFound(str(case_id))

    stmt = select(CaseEvidence).where(CaseEvidence.case_id == case_id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = list(
        db.scalars(stmt.order_by(CaseEvidence.created_at).limit(limit).offset(offset)).all()
    )
    return rows, total
