import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EvidenceType = Literal[
    "transaction",
    "risk_score",
    "shap_explanation",
    "graph_neighborhood",
    "graph_metrics",
    "fund_flow",
    "historical_stats",
    "analyst_note",
]


class CaseEvidenceAttachRequest(BaseModel):
    """`source_id` names the real record the evidence is resolved from —
    a transaction id for `transaction`, a risk_score id for `risk_score`/
    `shap_explanation`, or an account id for the graph/history types.
    Everything in `evidence_payload` is computed server-side from that
    record by `app/services/evidence.py`, never taken from this request
    (§7 "do not fabricate evidence") — the one exception is `analyst_note`,
    where `body` *is* the content, since a note is the analyst's own
    statement, not a claim about external evidence.
    """

    evidence_type: EvidenceType
    source_id: uuid.UUID | None = None
    body: str | None = Field(default=None, min_length=1)

    # Optional parameters for the graph-derived evidence types, passed
    # straight through to the same bounded-query functions the `/graph/*`
    # endpoints use (`app/services/graph_analytics.py`) — so an attached
    # "graph_neighborhood" snapshot used the identical, tested code path.
    hops: int | None = Field(default=None, ge=1, le=4)
    as_of_step: int | None = Field(default=None, ge=0)
    max_hops: int | None = Field(default=None, ge=1, le=5)
    max_branches: int | None = Field(default=None, ge=1, le=10)


class CaseEvidenceRead(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    evidence_type: str
    source_reference: str
    evidence_payload: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class CaseEvidenceListResponse(BaseModel):
    items: list[CaseEvidenceRead]
    total: int
    limit: int
    offset: int
