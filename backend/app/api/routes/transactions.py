from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import ServicePrincipal, require_role, require_service
from app.db.models import Transaction, User
from app.db.session import get_db
from app.schemas.transaction import (
    TransactionIngestRequest,
    TransactionIngestResponse,
    TransactionListResponse,
    TransactionRead,
)
from app.services.ingestion import ingest_transactions

router = APIRouter(prefix="/transactions", tags=["transactions"])

_ANALYST_PLUS = require_role("analyst", "senior_analyst", "admin")


@router.post("/ingest", response_model=TransactionIngestResponse)
def ingest(
    request: TransactionIngestRequest,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[ServicePrincipal, Depends(require_service)],
) -> TransactionIngestResponse:
    """Batch ingest from the PaySim replay (`ml/data/replay.py`). Writes
    `app.accounts`/`app.transactions` only — see
    `app/services/ingestion.py`. `service`-role only (docs/api-contracts.md
    §0), same machine credential as `POST /risk-scores` — see
    `docs/authentication.md`.
    """
    return ingest_transactions(db, request.transactions)


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
    account_id: UUID | None = None,
    type: str | None = None,  # noqa: A002  (matches the documented query param name)
) -> TransactionListResponse:
    stmt = select(Transaction)
    if account_id is not None:
        stmt = stmt.where(
            (Transaction.origin_account_id == account_id)
            | (Transaction.dest_account_id == account_id)
        )
    if type is not None:
        stmt = stmt.where(Transaction.type == type)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Transaction.step).limit(limit).offset(offset)).all()

    return TransactionListResponse(
        items=[TransactionRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(
    transaction_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> TransactionRead:
    row = db.get(Transaction, transaction_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="transaction not found")
    return TransactionRead.model_validate(row)
