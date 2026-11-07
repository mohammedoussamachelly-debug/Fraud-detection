import uuid
from datetime import datetime

from pydantic import BaseModel


class AccountRead(BaseModel):
    id: uuid.UUID
    external_ref: str
    account_type: str
    first_seen_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class AccountListResponse(BaseModel):
    items: list[AccountRead]
    total: int
    limit: int
    offset: int
