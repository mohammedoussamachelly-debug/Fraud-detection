from pydantic import BaseModel, Field

from app.schemas.transaction import TransactionType


class RiskScoreRequest(BaseModel):
    transaction_id: str = Field(min_length=1)
    transaction_type: TransactionType
    amount: float = Field(ge=0)
    sender_id: str = Field(min_length=1)
    receiver_id: str = Field(min_length=1)
    step: int = Field(ge=0)
    oldbalanceOrg: float = Field(ge=0)  # noqa: N815  (matches PaySim's own field name, by design)
    oldbalanceDest: float = Field(ge=0)  # noqa: N815
    include_explanation: bool = False


class ShapContribution(BaseModel):
    feature: str
    value: float | str
    shap_contribution: float
    direction: str  # "increases_risk" | "decreases_risk"


class RiskExplanation(BaseModel):
    base_value: float
    contributions: list[ShapContribution]


class RiskScoreResponse(BaseModel):
    transaction_id: str
    risk_score: float
    risk_level: str  # "low" | "medium" | "high"
    model_version: str
    threshold: float
    explanation: RiskExplanation | None = None
