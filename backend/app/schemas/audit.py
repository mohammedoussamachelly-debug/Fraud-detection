import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditLogEntryRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    event_metadata: dict
    occurred_at: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogEntryRead]
    total: int
    limit: int
    offset: int
