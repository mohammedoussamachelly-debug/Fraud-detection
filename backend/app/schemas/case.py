import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

CaseStatus = Literal["open", "investigating", "pending_review", "resolved", "closed"]
CasePriority = Literal["low", "medium", "high", "critical"]


class CaseRead(BaseModel):
    id: uuid.UUID
    status: str
    priority: str
    assigned_analyst_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    model_config = {"from_attributes": True}


class CaseListResponse(BaseModel):
    items: list[CaseRead]
    total: int
    limit: int
    offset: int


class CaseCreateRequest(BaseModel):
    alert_ids: list[uuid.UUID] = Field(min_length=1)
    priority: CasePriority = "medium"


class CaseUpdateRequest(BaseModel):
    """Only non-decision status transitions go through this endpoint —
    moving to `resolved` happens only via `POST /cases/{id}/decision`
    (`app/services/cases.py::record_decision`), never here, per CLAUDE.md's
    human-in-the-loop rule.
    """

    status: CaseStatus | None = None
    priority: CasePriority | None = None
    assigned_analyst_id: uuid.UUID | None = None


class CaseAlertLink(BaseModel):
    alert_id: uuid.UUID
    linked_at: datetime

    model_config = {"from_attributes": True}


class CaseDetailResponse(CaseRead):
    alerts: list[CaseAlertLink]
