"""Read models for the analyst workspace; existing domain APIs remain available."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.risk_score_record import RiskScoreRecordRead
from app.schemas.transaction import TransactionRead


class Activity(BaseModel):
    transaction: TransactionRead
    sender: str
    recipient: str
    risk: RiskScoreRecordRead | None
    alert_id: UUID | None = None
    case_id: UUID | None = None
    synthetic: bool


class InboxEntry(BaseModel):
    id: UUID
    description: str
    severity: str
    status: str
    created_at: datetime
    source: str
    activity: Activity


class ActivityPage(BaseModel):
    items: list[Activity]
    total: int
    limit: int
    offset: int


class InboxPage(BaseModel):
    items: list[InboxEntry]
    total: int
    limit: int
    offset: int


class Dashboard(BaseModel):
    transactions: int
    attention: int
    investigations: int
    review: int
    queue: list[InboxEntry]


class CaseSummary(BaseModel):
    id: UUID
    title: str
    status: str
    priority: str
    created_at: datetime


class CasePage(BaseModel):
    items: list[CaseSummary]
    total: int
    limit: int
    offset: int


class CaseContext(BaseModel):
    case: CaseSummary
    activities: list[Activity]
    history: dict
    run_id: UUID | None


class OpenCase(BaseModel):
    case_id: UUID
    created: bool


class OpenReport(BaseModel):
    run_id: UUID
    status: str
