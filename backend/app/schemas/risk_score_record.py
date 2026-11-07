import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.risk import RiskExplanation


class RiskScorePersistRequest(BaseModel):
    """Score (or return the already-persisted score for) an ingested
    transaction. Unlike `POST /risk/score` (stateless, §4.1 of
    docs/api-contracts.md), `transaction_id` here must already exist in
    `app.transactions` — all scoring inputs are read from that row, never
    resupplied by the caller, so there is no way to persist a score for
    facts that don't match the ingested transaction.
    """

    transaction_id: uuid.UUID
    include_explanation: bool = False


class RiskScoreRecordRead(BaseModel):
    # float, not Decimal: matches the existing `/risk/score` response
    # convention (app/schemas/risk.py) so callers handle both the same
    # way; the DB column (app/db/models/risk_score.py) stays Numeric for
    # storage precision — this is purely an API-shape choice.
    id: uuid.UUID
    transaction_id: uuid.UUID
    risk_score: float
    risk_level: str
    model_version: str
    threshold_used: float
    explanation: RiskExplanation | None = None
    scored_at: datetime

    model_config = {"from_attributes": True}


class AlertSummary(BaseModel):
    id: uuid.UUID
    alert_type: str
    severity: str
    status: str

    model_config = {"from_attributes": True}


class RiskScorePersistResponse(BaseModel):
    risk_score: RiskScoreRecordRead
    alert: AlertSummary | None
    created: bool
