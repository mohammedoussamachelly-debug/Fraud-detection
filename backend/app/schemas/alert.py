import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AlertStatus = Literal["open", "triaged", "escalated", "dismissed"]


class AlertRead(BaseModel):
    id: uuid.UUID
    transaction_id: uuid.UUID
    risk_score_id: uuid.UUID | None
    alert_type: str
    severity: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    items: list[AlertRead]
    total: int
    limit: int
    offset: int


class AlertStatusUpdate(BaseModel):
    status: AlertStatus
