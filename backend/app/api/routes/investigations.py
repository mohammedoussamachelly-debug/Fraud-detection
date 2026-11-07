from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.investigation import (
    AgentEvidenceRefRead,
    AgentStepRead,
    InvestigationDetailResponse,
    RequestRevisionRequest,
)
from app.services import investigations as investigations_service

router = APIRouter(prefix="/investigations", tags=["investigations"])

_ANALYST_PLUS = require_role("analyst", "senior_analyst", "admin")


def _to_detail(db: Session, run_id: UUID) -> InvestigationDetailResponse:
    run = investigations_service.get_investigation(db, run_id)
    steps = investigations_service.list_steps(db, run_id)
    refs = investigations_service.list_evidence_refs(db, run_id)
    return InvestigationDetailResponse(
        run_id=run.id,
        case_id=run.case_id,
        started_by_user_id=run.started_by_user_id,
        status=run.status,  # type: ignore[arg-type]
        model_provider=run.model_provider,
        model_name=run.model_name,
        prompt_version=run.prompt_version,
        revision_count=run.revision_count,
        review_feedback=run.review_feedback,
        draft_report=run.draft_report,
        final_report=run.final_report,
        error=run.error,
        started_at=run.started_at,
        completed_at=run.completed_at,
        steps=[AgentStepRead.model_validate(s) for s in steps],
        evidence_refs=[AgentEvidenceRefRead.model_validate(r) for r in refs],
    )


@router.get("/{run_id}", response_model=InvestigationDetailResponse)
def get_investigation(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> InvestigationDetailResponse:
    try:
        return _to_detail(db, run_id)
    except investigations_service.RunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="investigation run not found"
        ) from exc


@router.post("/{run_id}/approve", response_model=InvestigationDetailResponse)
def approve_investigation(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> InvestigationDetailResponse:
    """Finalizes the draft report as the case's investigation record.
    **Not** a case decision — never touches `Case.status` or creates a
    `CaseDecision`; only `POST /cases/{id}/decision` does that
    (`docs/agent-security.md`).
    """
    try:
        investigations_service.approve_investigation(db, run_id, actor_user_id=user.id)
        return _to_detail(db, run_id)
    except investigations_service.RunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="investigation run not found"
        ) from exc
    except investigations_service.InvalidRunTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"invalid run transition: {exc}"
        ) from exc


@router.post("/{run_id}/reject", response_model=InvestigationDetailResponse)
def reject_investigation(
    run_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> InvestigationDetailResponse:
    try:
        investigations_service.reject_investigation(db, run_id, actor_user_id=user.id)
        return _to_detail(db, run_id)
    except investigations_service.RunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="investigation run not found"
        ) from exc
    except investigations_service.InvalidRunTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"invalid run transition: {exc}"
        ) from exc


@router.post("/{run_id}/request-revision", response_model=InvestigationDetailResponse)
def request_revision(
    run_id: UUID,
    body: RequestRevisionRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> InvestigationDetailResponse:
    try:
        investigations_service.request_revision(
            db, run_id, actor_user_id=user.id, feedback=body.feedback
        )
        return _to_detail(db, run_id)
    except investigations_service.RunNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="investigation run not found"
        ) from exc
    except investigations_service.InvalidRunTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"invalid run transition: {exc}"
        ) from exc
    except investigations_service.RevisionLimitExceeded as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
