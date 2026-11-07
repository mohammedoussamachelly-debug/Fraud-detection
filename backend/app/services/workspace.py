"""Enriched read models and serialized, deduplicated workflow entry points."""

import uuid
from typing import TypeVar

from sqlalchemy import case as sql_case
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from app.db.base import Base
from app.db.models import (
    Account,
    AgentRun,
    Alert,
    Case,
    CaseAlert,
    CaseEvidence,
    DemoRecord,
    RiskScore,
    Transaction,
)
from app.demo.loader import register
from app.schemas.risk import RiskExplanation
from app.schemas.risk_score_record import RiskScoreRecordRead
from app.schemas.transaction import TransactionRead
from app.schemas.workspace import Activity, CaseContext, CaseSummary, InboxEntry
from app.services.audit import record_event
from app.services.history import get_sender_history
from app.services.investigations import start_investigation

T = TypeVar("T", bound=Base)


def related(db: Session, model: type[T], identifier: uuid.UUID) -> T:
    item = db.get(model, identifier)
    assert item is not None  # enforced by operational foreign keys
    return item


DESCRIPTIONS = {
    "model_threshold": "Model score crossed the review threshold",
    "demo_rule_unusual": "Larger-than-usual business transfer",
    "demo_rule_incoming": "Multiple senders paid one collection account",
    "demo_rule_redistribution": "Received funds moved to several accounts",
    "demo_rule_linked": "Connected transfers need a closer look",
}


def label(reference: str) -> str:
    return reference.split(":", 2)[-1] if "DEMO:" in reference else reference


def activity(db: Session, tx: Transaction) -> Activity:
    score = db.scalar(
        select(RiskScore)
        .where(RiskScore.transaction_id == tx.id)
        .order_by(RiskScore.scored_at.desc(), RiskScore.id)
        .limit(1)
    )
    alert = db.scalar(
        select(Alert)
        .where(Alert.transaction_id == tx.id)
        .order_by(Alert.created_at, Alert.id)
        .limit(1)
    )
    case_id = db.scalar(
        select(CaseAlert.case_id)
        .join(Alert, Alert.id == CaseAlert.alert_id)
        .where(Alert.transaction_id == tx.id)
        .order_by(CaseAlert.linked_at, CaseAlert.case_id)
        .limit(1)
    )
    risk = None
    if score:
        risk = RiskScoreRecordRead(
            id=score.id,
            transaction_id=tx.id,
            risk_score=float(score.risk_score),
            risk_level=score.risk_level,
            model_version=score.model_version,
            threshold_used=float(score.threshold_used),
            scored_at=score.scored_at,
            explanation=RiskExplanation.model_validate(score.shap_values)
            if score.shap_values
            else None,
        )
    return Activity(
        transaction=TransactionRead.model_validate(tx),
        sender=label(related(db, Account, tx.origin_account_id).external_ref),
        recipient=label(related(db, Account, tx.dest_account_id).external_ref),
        risk=risk,
        alert_id=alert.id if alert else None,
        case_id=case_id,
        synthetic=tx.external_ref.startswith("DEMO:"),
    )


def inbox_entry(db: Session, alert: Alert) -> InboxEntry:
    item = activity(db, related(db, Transaction, alert.transaction_id))
    item.alert_id = alert.id
    item.case_id = db.scalar(
        select(CaseAlert.case_id)
        .where(CaseAlert.alert_id == alert.id)
        .order_by(CaseAlert.linked_at, CaseAlert.case_id)
        .limit(1)
    )
    return InboxEntry(
        id=alert.id,
        description=DESCRIPTIONS.get(alert.alert_type, alert.alert_type.replace("_", " ")),
        severity=alert.severity,
        status=alert.status,
        created_at=alert.created_at,
        source="Demonstration rule"
        if alert.alert_type.startswith("demo_rule_")
        else "Model threshold"
        if alert.alert_type == "model_threshold"
        else "Rule",
        activity=item,
    )


def inbox(
    db: Session,
    status: str | None,
    severity: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> dict:
    sender, recipient = aliased(Account), aliased(Account)
    query = (
        select(Alert)
        .join(Transaction, Alert.transaction_id == Transaction.id)
        .join(sender, sender.id == Transaction.origin_account_id)
        .join(recipient, recipient.id == Transaction.dest_account_id)
    )
    if status == "attention":
        query = query.where(Alert.status.in_(["open", "triaged", "escalated"]))
    elif status:
        query = query.where(Alert.status == status)
    if severity:
        query = query.where(Alert.severity == severity)
    if search:
        query = query.where(
            or_(
                sender.external_ref.icontains(search, autoescape=True),
                recipient.external_ref.icontains(search, autoescape=True),
                Alert.alert_type.icontains(search, autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    priority = sql_case(
        (Alert.severity == "critical", 0),
        (Alert.severity == "high", 1),
        (Alert.severity == "medium", 2),
        else_=3,
    )
    rows = db.scalars(
        query.order_by(priority, Alert.created_at.desc(), Alert.id).limit(limit).offset(offset)
    )
    return dict(items=[inbox_entry(db, a) for a in rows], total=total, limit=limit, offset=offset)


def transactions(
    db: Session,
    search: str | None,
    kind: str | None,
    account_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> dict:
    sender, recipient = aliased(Account), aliased(Account)
    query = (
        select(Transaction)
        .join(sender, sender.id == Transaction.origin_account_id)
        .join(recipient, recipient.id == Transaction.dest_account_id)
    )
    if search:
        query = query.where(
            or_(
                Transaction.external_ref.icontains(search, autoescape=True),
                sender.external_ref.icontains(search, autoescape=True),
                recipient.external_ref.icontains(search, autoescape=True),
            )
        )
    if kind:
        query = query.where(Transaction.type == kind)
    if account_id:
        query = query.where(
            or_(
                Transaction.origin_account_id == account_id,
                Transaction.dest_account_id == account_id,
            )
        )
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(
        query.order_by(Transaction.step.desc(), Transaction.id).limit(limit).offset(offset)
    )
    return dict(items=[activity(db, t) for t in rows], total=total, limit=limit, offset=offset)


def summary(db: Session, item: Case) -> CaseSummary:
    tx = db.scalar(
        select(Transaction)
        .join(Alert, Alert.transaction_id == Transaction.id)
        .join(CaseAlert, CaseAlert.alert_id == Alert.id)
        .where(CaseAlert.case_id == item.id)
        .order_by(Transaction.step, Transaction.id)
        .limit(1)
    )
    title = (
        f"Review transfers from {label(related(db, Account, tx.origin_account_id).external_ref)}"
        if tx
        else "Activity review"
    )
    return CaseSummary(
        id=item.id,
        title=title,
        status=item.status,
        priority=item.priority,
        created_at=item.created_at,
    )


def context(db: Session, item: Case) -> CaseContext:
    txs = db.scalars(
        select(Transaction)
        .join(Alert, Alert.transaction_id == Transaction.id)
        .join(CaseAlert, CaseAlert.alert_id == Alert.id)
        .where(CaseAlert.case_id == item.id)
        .distinct()
        .order_by(Transaction.step, Transaction.id)
    ).all()
    history = (
        get_sender_history(
            db, related(db, Account, txs[0].origin_account_id).external_ref, txs[0].step
        )
        if txs
        else {}
    )
    run_id = db.scalar(
        select(AgentRun.id)
        .where(AgentRun.case_id == item.id)
        .order_by(AgentRun.started_at.desc(), AgentRun.id)
        .limit(1)
    )
    return CaseContext(
        case=summary(db, item),
        activities=[activity(db, t) for t in txs],
        history=history,
        run_id=run_id,
    )


def investigate(db: Session, alert: Alert, actor_id: uuid.UUID) -> dict:
    # A payment may have both a model alert and a demonstration-rule alert.
    # Serialize by payment so simultaneous entry through either reuses one case.
    db.execute(
        select(Transaction.id).where(Transaction.id == alert.transaction_id).with_for_update()
    )
    case_id = db.scalar(
        select(CaseAlert.case_id)
        .where(CaseAlert.alert_id == alert.id)
        .order_by(CaseAlert.linked_at, CaseAlert.case_id)
        .limit(1)
    )
    if case_id is None:
        case_id = db.scalar(
            select(CaseAlert.case_id)
            .join(Alert, Alert.id == CaseAlert.alert_id)
            .where(Alert.transaction_id == alert.transaction_id)
            .order_by(CaseAlert.linked_at, CaseAlert.case_id)
            .limit(1)
        )
    created = case_id is None
    if created:
        item = Case(priority=alert.severity, status="investigating", assigned_analyst_id=actor_id)
        db.add(item)
        db.flush()
        case_id = item.id
        owner = db.scalar(
            select(DemoRecord.batch_id).where(
                DemoRecord.entity_type == "alert", DemoRecord.entity_id == alert.id
            )
        )
        if owner:
            register(db, owner, "case", [case_id])
        record_event(
            db,
            user_id=actor_id,
            action="case_created",
            entity_type="case",
            entity_id=case_id,
            metadata={"alert_id": str(alert.id), "entry_point": "workspace"},
        )
    db.execute(select(Case.id).where(Case.id == case_id).with_for_update())
    if db.get(CaseAlert, (case_id, alert.id)) is None:
        db.add(CaseAlert(case_id=case_id, alert_id=alert.id))
        record_event(
            db,
            user_id=actor_id,
            action="alert_linked",
            entity_type="case",
            entity_id=case_id,
            metadata={"alert_id": str(alert.id)},
        )
    tx = related(db, Transaction, alert.transaction_id)
    entries = [
        (
            "transaction",
            f"transaction:{tx.id}",
            TransactionRead.model_validate(tx).model_dump(mode="json"),
        )
    ]
    if alert.risk_score_id:
        score = related(db, RiskScore, alert.risk_score_id)
        entries.append(
            (
                "risk_score",
                f"risk_score:{score.id}",
                dict(
                    transaction_id=str(tx.id),
                    risk_score=float(score.risk_score),
                    risk_level=score.risk_level,
                    model_version=score.model_version,
                    threshold_used=float(score.threshold_used),
                ),
            )
        )
        if score.shap_values:
            entries.append(("shap_explanation", f"risk_score:{score.id}", score.shap_values))
    for kind, source, payload in entries:
        if not db.scalar(
            select(CaseEvidence.id).where(
                CaseEvidence.case_id == case_id,
                CaseEvidence.evidence_type == kind,
                CaseEvidence.source_reference == source,
            )
        ):
            evidence = CaseEvidence(
                case_id=case_id,
                evidence_type=kind,
                source_reference=source,
                evidence_payload=payload,
            )
            db.add(evidence)
            db.flush()
            record_event(
                db,
                user_id=actor_id,
                action="evidence_attached",
                entity_type="case",
                entity_id=case_id,
                metadata={"evidence_id": str(evidence.id), "source_reference": source},
            )
    db.commit()
    return dict(case_id=case_id, created=created)


def report(db: Session, item: Case, actor_id: uuid.UUID) -> dict:
    db.execute(select(Case.id).where(Case.id == item.id).with_for_update())
    run = db.scalar(
        select(AgentRun)
        .where(AgentRun.case_id == item.id)
        .order_by(AgentRun.started_at.desc(), AgentRun.id)
        .limit(1)
    )
    if run is None:
        run = start_investigation(db, item.id, actor_id)
    result = dict(run_id=run.id, status=run.status)
    db.commit()
    return result
