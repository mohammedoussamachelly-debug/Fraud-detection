from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_db
from app.graph.build import MAX_HOPS as NEIGHBORHOOD_MAX_HOPS
from app.graph.fund_flow import MAX_BRANCHES as FUND_FLOW_MAX_BRANCHES
from app.graph.fund_flow import MAX_HOPS as FUND_FLOW_MAX_HOPS
from app.schemas.graph import (
    AccountGraphMetricsResponse,
    AccountGraphTransactionsResponse,
    AccountNeighborhoodResponse,
    FundFlowResponse,
)
from app.services import graph_analytics

router = APIRouter(prefix="/graph", tags=["graph"])

_ANALYST_PLUS = require_role("analyst", "senior_analyst", "admin")


@router.get("/accounts/{account_id}", response_model=AccountNeighborhoodResponse)
def get_account_neighborhood(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    hops: Annotated[int, Query(ge=1, le=NEIGHBORHOOD_MAX_HOPS)] = 2,
    as_of_step: Annotated[int | None, Query(ge=0)] = None,
) -> AccountNeighborhoodResponse:
    try:
        return graph_analytics.get_account_neighborhood(
            db, account_id, hops=hops, as_of_step=as_of_step
        )
    except graph_analytics.AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="account not found"
        ) from exc


@router.get("/accounts/{account_id}/metrics", response_model=AccountGraphMetricsResponse)
def get_account_metrics(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    as_of_step: Annotated[int | None, Query(ge=0)] = None,
) -> AccountGraphMetricsResponse:
    try:
        return graph_analytics.get_account_metrics(db, account_id, as_of_step=as_of_step)
    except graph_analytics.AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="account not found"
        ) from exc


@router.get("/accounts/{account_id}/transactions", response_model=AccountGraphTransactionsResponse)
def get_account_graph_transactions(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    as_of_step: Annotated[int | None, Query(ge=0)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AccountGraphTransactionsResponse:
    try:
        return graph_analytics.get_account_transactions(
            db, account_id, as_of_step=as_of_step, limit=limit, offset=offset
        )
    except graph_analytics.AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="account not found"
        ) from exc


@router.get("/accounts/{account_id}/fund-flow", response_model=FundFlowResponse)
def get_account_fund_flow(
    account_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    as_of_step: Annotated[int | None, Query(ge=0)] = None,
    max_hops: Annotated[int, Query(ge=1, le=FUND_FLOW_MAX_HOPS)] = 3,
    max_branches: Annotated[int, Query(ge=1, le=FUND_FLOW_MAX_BRANCHES)] = 3,
) -> FundFlowResponse:
    try:
        return graph_analytics.get_account_fund_flow(
            db, account_id, as_of_step=as_of_step, max_hops=max_hops, max_branches=max_branches
        )
    except graph_analytics.AccountNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="account not found"
        ) from exc
