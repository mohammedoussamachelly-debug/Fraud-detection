import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

TransactionType = Literal["CASH_IN", "CASH_OUT", "DEBIT", "PAYMENT", "TRANSFER"]


class TransactionIngestItem(BaseModel):
    """One PaySim row, as sent by the replay script (`ml/data/replay.py`).
    No `isFraud`/`isFlaggedFraud` field exists here by design — see
    docs/database-design.md §3; the ingest path has nothing to drop even by
    mistake because the shape never admits those fields in the first place.
    """

    external_ref: str = Field(min_length=1)
    step: int = Field(ge=0)
    type: TransactionType
    amount: Decimal = Field(ge=0)
    origin_external_ref: str = Field(min_length=1)
    dest_external_ref: str = Field(min_length=1)
    origin_balance_before: Decimal = Field(ge=0)
    origin_balance_after: Decimal = Field(ge=0)
    dest_balance_before: Decimal = Field(ge=0)
    dest_balance_after: Decimal = Field(ge=0)


class TransactionIngestRequest(BaseModel):
    transactions: list[TransactionIngestItem] = Field(min_length=1, max_length=5000)


class TransactionIngestResponse(BaseModel):
    received: int
    inserted: int
    skipped_existing: int
    accounts_created: int


class TransactionRead(BaseModel):
    id: uuid.UUID
    external_ref: str
    step: int
    occurred_at: datetime
    type: str
    amount: Decimal
    origin_account_id: uuid.UUID
    dest_account_id: uuid.UUID
    origin_balance_before: Decimal
    origin_balance_after: Decimal
    dest_balance_before: Decimal
    dest_balance_after: Decimal

    model_config = {"from_attributes": True}


class TransactionListResponse(BaseModel):
    items: list[TransactionRead]
    total: int
    limit: int
    offset: int
