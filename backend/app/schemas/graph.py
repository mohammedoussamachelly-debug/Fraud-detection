import uuid
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.transaction import TransactionRead


class GraphNode(BaseModel):
    id: uuid.UUID
    external_ref: str
    account_type: str


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    transaction_id: uuid.UUID
    external_ref: str
    amount: Decimal
    step: int
    type: str


class AccountNeighborhoodResponse(BaseModel):
    center_account_id: uuid.UUID
    hops: int
    as_of_step: int | None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    cycles: list[list[str]]
    truncated: bool
    disclaimer: str


class AccountGraphMetricsResponse(BaseModel):
    account_id: uuid.UUID
    as_of_step: int | None
    incoming_transaction_count: int
    outgoing_transaction_count: int
    unique_senders: int
    unique_recipients: int
    fan_in_pattern: bool
    fan_out_pattern: bool
    velocity_window_steps: int
    velocity_count: int
    truncated: bool
    disclaimer: str


class GraphTransactionRead(TransactionRead):
    direction: str  # "incoming" | "outgoing"


class AccountGraphTransactionsResponse(BaseModel):
    items: list[GraphTransactionRead]
    total: int
    limit: int
    offset: int
    as_of_step: int | None


class FundFlowStep(BaseModel):
    transaction_id: uuid.UUID
    transaction_external_ref: str
    from_account_id: uuid.UUID
    to_account_id: uuid.UUID
    amount: Decimal
    step: int


class FundFlowPath(BaseModel):
    steps: list[FundFlowStep]


class FundFlowResponse(BaseModel):
    source_account_id: uuid.UUID
    as_of_step: int | None
    max_hops: int
    max_branches: int
    paths: list[FundFlowPath]
    truncated: bool
    disclaimer: str
