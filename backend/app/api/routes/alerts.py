from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.alert import AlertListResponse, AlertRead, AlertStatusUpdate
from app.services import alerts as alerts_service

router = APIRouter(prefix="/alerts", tags=["alerts"])

_ANALYST_PLUS = require_role("analyst", "senior_analyst", "admin")


@router.get("", response_model=AlertListResponse)
def list_alerts(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    severity: str | None = None,
    created_from: date | None = None,
    created_to: date | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AlertListResponse:
    return alerts_service.list_alerts(
        db,
        status=status_filter,
        severity=severity,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
        offset=offset,
    )


@router.get("/{alert_id}", response_model=AlertRead)
def get_alert(
    alert_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> AlertRead:
    try:
        return AlertRead.model_validate(alerts_service.get_alert(db, alert_id))
    except alerts_service.AlertNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="alert not found"
        ) from exc


@router.patch("/{alert_id}", response_model=AlertRead)
def update_alert(
    alert_id: UUID,
    body: AlertStatusUpdate,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> AlertRead:
    try:
        updated = alerts_service.update_alert_status(db, alert_id, body.status)
        return AlertRead.model_validate(updated)
    except alerts_service.AlertNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="alert not found"
        ) from exc
