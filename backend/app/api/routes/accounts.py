from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import Account, User
from app.db.session import get_db
from app.schemas.account import AccountListResponse, AccountRead

router = APIRouter(prefix="/accounts", tags=["accounts"])

_ANALYST_PLUS = require_role("analyst", "senior_analyst", "admin")


@router.get("", response_model=AccountListResponse)
def list_accounts(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    external_ref: str | None = None,
    account_type: str | None = None,
) -> AccountListResponse:
    stmt = select(Account)
    if external_ref is not None:
        stmt = stmt.where(Account.external_ref == external_ref)
    if account_type is not None:
        stmt = stmt.where(Account.account_type == account_type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Account.first_seen_at).limit(limit).offset(offset)).all()

    return AccountListResponse(
        items=[AccountRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{account_id}", response_model=AccountRead)
def get_account(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> AccountRead:
    row = db.get(Account, account_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="account not found")
    return AccountRead.model_validate(row)
