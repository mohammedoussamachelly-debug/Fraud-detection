"""Persists a `/risk/score`-equivalent result for an already-ingested
transaction, and raises a deduplicated alert when it crosses the active
threshold. Reuses the exact Phase 3 scoring pipeline
(`app/services/risk_scoring.py::score_transaction`) rather than
re-deriving features a second way — the leakage-safety guarantees of that
pipeline (pre-event history only, never the model's own training labels)
carry over unchanged.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Account, Alert, RiskScore, Transaction
from app.ml.inference import ModelArtifact
from app.schemas.risk import RiskExplanation, RiskScoreRequest
from app.schemas.risk_score_record import (
    AlertSummary,
    RiskScorePersistResponse,
    RiskScoreRecordRead,
)
from app.services import audit
from app.services.alerting import ALERT_TYPE_MODEL_THRESHOLD, severity_for_score, should_alert
from app.services.risk_scoring import score_transaction


class TransactionNotFound(Exception):
    pass


def _build_request(transaction: Transaction, origin: Account, dest: Account) -> RiskScoreRequest:
    return RiskScoreRequest(
        transaction_id=str(transaction.id),
        transaction_type=transaction.type,  # type: ignore[arg-type]
        amount=float(transaction.amount),
        sender_id=origin.external_ref,
        receiver_id=dest.external_ref,
        step=transaction.step,
        oldbalanceOrg=float(transaction.origin_balance_before),
        oldbalanceDest=float(transaction.dest_balance_before),
        include_explanation=False,  # overridden by the caller when requested
    )


def _existing_alert_for(db: Session, transaction_id: uuid.UUID) -> Alert | None:
    return db.scalar(
        select(Alert).where(
            Alert.transaction_id == transaction_id, Alert.alert_type == ALERT_TYPE_MODEL_THRESHOLD
        )
    )


def persist_risk_score(
    db: Session,
    artifact: ModelArtifact,
    transaction_id: uuid.UUID,
    include_explanation: bool,
    actor_user_id: uuid.UUID | None,
) -> RiskScorePersistResponse:
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise TransactionNotFound(str(transaction_id))

    existing = db.scalar(
        select(RiskScore).where(
            RiskScore.transaction_id == transaction_id,
            RiskScore.model_version == artifact.version_label,
        )
    )
    if existing is not None:
        alert = _existing_alert_for(db, transaction_id)
        return _to_response(existing, alert, created=False)

    origin = db.get(Account, transaction.origin_account_id)
    dest = db.get(Account, transaction.dest_account_id)
    assert origin is not None and dest is not None  # FK-guaranteed by the schema

    request = _build_request(transaction, origin, dest)
    request.include_explanation = include_explanation
    scored = score_transaction(db, artifact, request)

    risk_score = RiskScore(
        transaction_id=transaction_id,
        risk_score=scored.risk_score,
        risk_level=scored.risk_level,
        model_version=scored.model_version,
        threshold_used=scored.threshold,
        shap_values=scored.explanation.model_dump() if scored.explanation else None,
    )
    db.add(risk_score)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race with a concurrent identical request: the unique
        # constraint on (transaction_id, model_version) caught it. Roll
        # back this insert and return the row the other request created —
        # same idempotency guarantee, just resolved at the DB layer instead
        # of the earlier SELECT.
        db.rollback()
        existing = db.scalar(
            select(RiskScore).where(
                RiskScore.transaction_id == transaction_id,
                RiskScore.model_version == artifact.version_label,
            )
        )
        assert existing is not None
        alert = _existing_alert_for(db, transaction_id)
        return _to_response(existing, alert, created=False)

    audit.record_event(
        db,
        user_id=actor_user_id,
        action="risk_score_persisted",
        entity_type="risk_score",
        entity_id=risk_score.id,
        metadata={"transaction_id": str(transaction_id), "model_version": scored.model_version},
    )

    alert = None
    if should_alert(scored.risk_level):
        alert = _existing_alert_for(db, transaction_id)
        if alert is None:
            alert = Alert(
                transaction_id=transaction_id,
                risk_score_id=risk_score.id,
                alert_type=ALERT_TYPE_MODEL_THRESHOLD,
                severity=severity_for_score(scored.risk_score, scored.threshold),
            )
            db.add(alert)
            try:
                db.flush()
            except IntegrityError:
                db.rollback()
                alert = _existing_alert_for(db, transaction_id)
            else:
                audit.record_event(
                    db,
                    user_id=actor_user_id,
                    action="alert_created",
                    entity_type="alert",
                    entity_id=alert.id,
                    metadata={"transaction_id": str(transaction_id), "severity": alert.severity},
                )

    db.commit()
    return _to_response(risk_score, alert, created=True)


def _to_response(
    risk_score: RiskScore, alert: Alert | None, created: bool
) -> RiskScorePersistResponse:
    explanation = (
        RiskExplanation.model_validate(risk_score.shap_values) if risk_score.shap_values else None
    )
    record = RiskScoreRecordRead(
        id=risk_score.id,
        transaction_id=risk_score.transaction_id,
        risk_score=float(risk_score.risk_score),
        risk_level=risk_score.risk_level,
        model_version=risk_score.model_version,
        threshold_used=float(risk_score.threshold_used),
        explanation=explanation,
        scored_at=risk_score.scored_at,
    )
    alert_summary = AlertSummary.model_validate(alert) if alert else None
    return RiskScorePersistResponse(risk_score=record, alert=alert_summary, created=created)
