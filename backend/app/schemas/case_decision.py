import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

DecisionValue = Literal["confirmed_fraud", "not_fraud", "dismissed"]


class CaseDecisionRequest(BaseModel):
    decision: DecisionValue
    # "rationale required, min length enforced" — docs/api-contracts.md §6.
    rationale: str = Field(min_length=10)


class CaseDecisionRead(BaseModel):
    id: uuid.UUID
    case_id: uuid.UUID
    decided_by_user_id: uuid.UUID
    decision: str
    rationale: str
    decided_at: datetime

    model_config = {"from_attributes": True}
