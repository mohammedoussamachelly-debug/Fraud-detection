import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal[
    "running", "awaiting_approval", "approved", "rejected", "revision_requested", "failed"
]


class StartInvestigationResponse(BaseModel):
    run_id: uuid.UUID
    status: RunStatus


class AgentStepRead(BaseModel):
    id: uuid.UUID
    node_name: str
    attempt: int
    status: str
    tool_calls: list[dict]
    output: dict | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AgentEvidenceRefRead(BaseModel):
    id: uuid.UUID
    evidence_type: str
    source_reference: str
    summary: str
    collected_by_node: str
    created_at: datetime

    model_config = {"from_attributes": True}


class InvestigationDetailResponse(BaseModel):
    run_id: uuid.UUID
    case_id: uuid.UUID
    started_by_user_id: uuid.UUID
    status: RunStatus
    model_provider: str
    model_name: str
    prompt_version: str
    revision_count: int
    review_feedback: list[str]
    draft_report: dict | None
    final_report: dict | None
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    steps: list[AgentStepRead]
    evidence_refs: list[AgentEvidenceRefRead]


class RequestRevisionRequest(BaseModel):
    feedback: str = Field(min_length=1)


class InvestigationSummary(BaseModel):
    """Lightweight per-run summary for `GET /cases/{id}/investigations` —
    the full step/evidence/report detail stays on
    `GET /investigations/{run_id}` (§6.1) so listing a case's run history
    doesn't require re-fetching every step of every run.
    """

    run_id: uuid.UUID
    case_id: uuid.UUID
    started_by_user_id: uuid.UUID
    status: RunStatus
    revision_count: int
    started_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class InvestigationListResponse(BaseModel):
    items: list[InvestigationSummary]
    total: int
    limit: int
    offset: int
