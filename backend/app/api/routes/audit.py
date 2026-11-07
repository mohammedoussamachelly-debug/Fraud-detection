from datetime import UTC, date, datetime, time
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import AuditLogEntry, User
from app.db.session import get_db
from app.schemas.audit import AuditLogEntryRead, AuditLogListResponse

router = APIRouter(tags=["audit"])

_ADMIN_ONLY = require_role("admin")


@router.get("/audit-log", response_model=AuditLogListResponse)
def list_audit_log(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ADMIN_ONLY)],
    user_id: UUID | None = None,
    action: str | None = None,
    occurred_from: date | None = None,
    occurred_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogListResponse:
    stmt = select(AuditLogEntry)
    if user_id is not None:
        stmt = stmt.where(AuditLogEntry.user_id == user_id)
    if action is not None:
        stmt = stmt.where(AuditLogEntry.action == action)
    if occurred_from is not None:
        stmt = stmt.where(
            AuditLogEntry.occurred_at >= datetime.combine(occurred_from, time.min, UTC)
        )
    if occurred_to is not None:
        stmt = stmt.where(AuditLogEntry.occurred_at <= datetime.combine(occurred_to, time.max, UTC))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    ordered = stmt.order_by(AuditLogEntry.occurred_at.desc()).limit(limit).offset(offset)
    rows = db.scalars(ordered).all()

    return AuditLogListResponse(
        items=[AuditLogEntryRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
