import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Alert
from app.schemas.alert import AlertListResponse, AlertRead


class AlertNotFound(Exception):
    pass


def list_alerts(
    db: Session,
    *,
    status: str | None,
    severity: str | None,
    created_from: date | None,
    created_to: date | None,
    limit: int,
    offset: int,
) -> AlertListResponse:
    stmt = select(Alert)
    if status is not None:
        stmt = stmt.where(Alert.status == status)
    if severity is not None:
        stmt = stmt.where(Alert.severity == severity)
    if created_from is not None:
        stmt = stmt.where(Alert.created_at >= datetime.combine(created_from, time.min, UTC))
    if created_to is not None:
        stmt = stmt.where(Alert.created_at <= datetime.combine(created_to, time.max, UTC))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Alert.created_at.desc()).limit(limit).offset(offset)).all()

    return AlertListResponse(
        items=[AlertRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


def get_alert(db: Session, alert_id: uuid.UUID) -> Alert:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise AlertNotFound(str(alert_id))
    return alert


def update_alert_status(db: Session, alert_id: uuid.UUID, new_status: str) -> Alert:
    alert = get_alert(db, alert_id)
    alert.status = new_status
    db.commit()
    return alert
