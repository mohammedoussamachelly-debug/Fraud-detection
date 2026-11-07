"""Case lifecycle: creation from alerts, assignment, status transitions,
and the human decision that resolves a case. Every mutation writes an
`audit_log_entries` row in the same transaction (CLAUDE.md: audit logging
for case decisions and, more broadly, every consequential action here).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Alert, Case, CaseAlert, CaseDecision, User
from app.schemas.case import CaseAlertLink, CaseDetailResponse, CaseListResponse, CaseRead
from app.schemas.case_decision import CaseDecisionRead
from app.services import audit

# "resolved" is reachable only through `record_decision`, never through
# `update_case` — see CaseUpdateRequest's docstring and CLAUDE.md's
# human-in-the-loop rule.
ALLOWED_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "open": {"investigating"},
    "investigating": {"pending_review", "open"},
    "pending_review": {"investigating"},
    "resolved": {"closed"},
    "closed": set(),
}


class CaseNotFound(Exception):
    pass


class AlertNotFound(Exception):
    pass


class UserNotFound(Exception):
    pass


class InvalidStatusTransition(Exception):
    pass


# Sentinel distinguishing "field omitted" from "field explicitly null" for
# `assigned_analyst_id` in `update_case`.
_UNSET = object()


def _case_alert_links(db: Session, case_id: uuid.UUID) -> list[CaseAlertLink]:
    rows = db.scalars(
        select(CaseAlert).where(CaseAlert.case_id == case_id).order_by(CaseAlert.linked_at)
    ).all()
    return [CaseAlertLink.model_validate(r) for r in rows]


def _to_detail(db: Session, case: Case) -> CaseDetailResponse:
    base = CaseRead.model_validate(case).model_dump()
    return CaseDetailResponse(**base, alerts=_case_alert_links(db, case.id))


def create_case(
    db: Session, *, alert_ids: list[uuid.UUID], priority: str, actor_user_id: uuid.UUID
) -> CaseDetailResponse:
    alerts = db.scalars(select(Alert).where(Alert.id.in_(alert_ids))).all()
    found_ids = {a.id for a in alerts}
    missing = set(alert_ids) - found_ids
    if missing:
        raise AlertNotFound(", ".join(str(i) for i in missing))

    case = Case(priority=priority)
    db.add(case)
    db.flush()

    for alert_id in alert_ids:
        db.add(CaseAlert(case_id=case.id, alert_id=alert_id))

    audit.record_event(
        db,
        user_id=actor_user_id,
        action="case_created",
        entity_type="case",
        entity_id=case.id,
        metadata={"alert_ids": [str(i) for i in alert_ids]},
    )
    db.commit()
    return _to_detail(db, case)


def get_case(db: Session, case_id: uuid.UUID) -> CaseDetailResponse:
    case = db.get(Case, case_id)
    if case is None:
        raise CaseNotFound(str(case_id))
    return _to_detail(db, case)


def list_cases(
    db: Session,
    *,
    status: str | None,
    assigned_analyst_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> CaseListResponse:
    stmt = select(Case)
    if status is not None:
        stmt = stmt.where(Case.status == status)
    if assigned_analyst_id is not None:
        stmt = stmt.where(Case.assigned_analyst_id == assigned_analyst_id)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Case.created_at.desc()).limit(limit).offset(offset)).all()

    return CaseListResponse(
        items=[CaseRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


def update_case(
    db: Session,
    case_id: uuid.UUID,
    *,
    fields_set: dict,
    actor_user_id: uuid.UUID,
) -> CaseDetailResponse:
    """`fields_set` is `CaseUpdateRequest.model_dump(exclude_unset=True)` —
    only keys the caller actually sent are present, so an omitted
    `assigned_analyst_id` leaves assignment untouched while an explicit
    `"assigned_analyst_id": null` unassigns (ordinary PATCH semantics).
    """
    case = db.get(Case, case_id)
    if case is None:
        raise CaseNotFound(str(case_id))

    changes: dict = {}

    status = fields_set.get("status")
    if status is not None and status != case.status:
        allowed = ALLOWED_STATUS_TRANSITIONS.get(case.status, set())
        if status not in allowed:
            raise InvalidStatusTransition(f"{case.status} -> {status}")
        case.status = status
        changes["status"] = status
        if status == "closed":
            case.closed_at = datetime.now(UTC)

    priority = fields_set.get("priority")
    if priority is not None and priority != case.priority:
        case.priority = priority
        changes["priority"] = priority

    if "assigned_analyst_id" in fields_set:
        assigned_analyst_id = fields_set["assigned_analyst_id"]
        if assigned_analyst_id is not None:
            assignee = db.get(User, assigned_analyst_id)
            if assignee is None:
                raise UserNotFound(str(assigned_analyst_id))
        case.assigned_analyst_id = assigned_analyst_id
        changes["assigned_analyst_id"] = str(assigned_analyst_id) if assigned_analyst_id else None

    if changes:
        case.updated_at = datetime.now(UTC)
        audit.record_event(
            db,
            user_id=actor_user_id,
            action="case_updated",
            entity_type="case",
            entity_id=case.id,
            metadata=changes,
        )
        db.commit()
    else:
        db.rollback()

    return _to_detail(db, case)


def record_decision(
    db: Session,
    case_id: uuid.UUID,
    *,
    decision: str,
    rationale: str,
    decided_by_user_id: uuid.UUID,
) -> CaseDecisionRead:
    """The only function in this codebase that may move a case to
    `resolved` — per CLAUDE.md, that transition requires exactly this
    recorded, accountable row. The route layer enforces that only
    `senior_analyst`/`admin` can call it at all (`app/api/deps.py`).
    """
    case = db.get(Case, case_id)
    if case is None:
        raise CaseNotFound(str(case_id))
    if case.status not in ("investigating", "pending_review"):
        raise InvalidStatusTransition(f"{case.status} -> resolved")

    record = CaseDecision(
        case_id=case_id,
        decided_by_user_id=decided_by_user_id,
        decision=decision,
        rationale=rationale,
    )
    db.add(record)
    case.status = "resolved"
    case.updated_at = datetime.now(UTC)
    db.flush()

    audit.record_event(
        db,
        user_id=decided_by_user_id,
        action="case_decision_recorded",
        entity_type="case",
        entity_id=case.id,
        metadata={"decision": decision, "case_decision_id": str(record.id)},
    )
    db.commit()
    return CaseDecisionRead.model_validate(record)


class DecisionNotFound(Exception):
    pass


def get_decision_for_case(db: Session, case_id: uuid.UUID) -> CaseDecisionRead:
    """`GET /cases/{id}/decision` (Phase 7 addition) — the case detail UI
    needs to re-display a recorded decision after a page reload, which
    `record_decision`'s return value alone can't do. The workflow only
    ever produces at most one `CaseDecision` per case in practice (it
    requires `investigating`/`pending_review`, and `resolved` can only
    move on to `closed`), but this reads the most recent one defensively
    rather than assuming that invariant holds forever.
    """
    if db.get(Case, case_id) is None:
        raise CaseNotFound(str(case_id))

    record = db.scalars(
        select(CaseDecision)
        .where(CaseDecision.case_id == case_id)
        .order_by(CaseDecision.decided_at.desc())
        .limit(1)
    ).first()
    if record is None:
        raise DecisionNotFound(str(case_id))
    return CaseDecisionRead.model_validate(record)
