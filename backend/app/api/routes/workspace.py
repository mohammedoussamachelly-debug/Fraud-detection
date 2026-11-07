from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import AgentRun, Alert, Case, DemoBatch, Transaction, User
from app.db.session import get_db
from app.schemas.workspace import (
    Activity,
    ActivityPage,
    CaseContext,
    CasePage,
    Dashboard,
    InboxPage,
    OpenCase,
    OpenReport,
)
from app.services import workspace

router = APIRouter(tags=["workspace"])
DB = Annotated[Session, Depends(get_db)]
Analyst = Annotated[User, Depends(require_role("analyst", "senior_analyst", "admin"))]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


def require(db, model, identifier):
    item = db.get(model, identifier)
    if item is None:
        raise HTTPException(404, "Record not found")
    return item


@router.get("/workspace/dashboard", response_model=Dashboard)
def dashboard(db: DB, user: Analyst):
    return dict(
        transactions=db.scalar(select(func.count()).select_from(Transaction)),
        attention=db.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.status.in_(["open", "triaged", "escalated"]))
        ),
        investigations=db.scalar(
            select(func.count()).select_from(Case).where(Case.status.in_(["open", "investigating"]))
        ),
        review=db.scalar(
            select(func.count(func.distinct(Case.id)))
            .select_from(Case)
            .outerjoin(AgentRun, AgentRun.case_id == Case.id)
            .where(
                (Case.status == "pending_review")
                | (
                    (AgentRun.status == "awaiting_approval")
                    & Case.status.not_in(["resolved", "closed"])
                )
            )
        ),
        queue=workspace.inbox(db, "attention", None, None, 5, 0)["items"],
    )


@router.get("/workspace/alerts", response_model=InboxPage)
def alerts(
    db: DB,
    user: Analyst,
    status: str | None = None,
    severity: str | None = None,
    search: str | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
):
    return workspace.inbox(db, status, severity, search, limit, offset)


@router.get("/workspace/transactions", response_model=ActivityPage)
def transactions(
    db: DB,
    user: Analyst,
    search: str | None = None,
    type: str | None = None,
    account_id: UUID | None = None,
    limit: Limit = 25,
    offset: Offset = 0,
):
    return workspace.transactions(db, search, type, account_id, limit, offset)


@router.get("/workspace/transactions/{transaction_id}", response_model=Activity)
def transaction(transaction_id: UUID, db: DB, user: Analyst):
    return workspace.activity(db, require(db, Transaction, transaction_id))


@router.get("/workspace/cases", response_model=CasePage)
def cases(db: DB, user: Analyst, status: str | None = None, limit: Limit = 25, offset: Offset = 0):
    query = select(Case)
    if status:
        query = query.where(Case.status == status)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    return dict(
        items=[
            workspace.summary(db, item)
            for item in db.scalars(
                query.order_by(Case.updated_at.desc(), Case.id).limit(limit).offset(offset)
            )
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/workspace/cases/{case_id}", response_model=CaseContext)
def case_context(case_id: UUID, db: DB, user: Analyst):
    return workspace.context(db, require(db, Case, case_id))


@router.post("/workspace/alerts/{alert_id}/investigate", response_model=OpenCase)
def investigate(alert_id: UUID, db: DB, user: Analyst):
    return workspace.investigate(db, require(db, Alert, alert_id), user.id)


@router.post("/workspace/cases/{case_id}/report", response_model=OpenReport)
def report(case_id: UUID, db: DB, user: Analyst):
    return workspace.report(db, require(db, Case, case_id), user.id)


@router.get("/demo/scenarios")
def scenarios(db: DB, user: Analyst):
    return {
        "items": [
            {**scenario, "batch": batch.id}
            for batch in db.scalars(select(DemoBatch).order_by(DemoBatch.id))
            for scenario in batch.scenarios
        ],
        "notice": (
            "Synthetic demonstration. Scores are genuine PaySim model predictions, "
            "not calibrated probabilities for this new distribution. "
            "Scenario rules describe patterns, not proof of crime."
        ),
    }


@router.get("/workspace/transactions/{transaction_id}/history")
def transaction_history(transaction_id: UUID, db: DB, user: Analyst):
    from app.db.models import Account
    from app.services.history import get_sender_history

    tx = require(db, Transaction, transaction_id)
    account = workspace.related(db, Account, tx.origin_account_id)
    return get_sender_history(db, account.external_ref, tx.step)
