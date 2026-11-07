from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.agents.llm import LLMProviderUnavailable
from app.api.deps import require_role
from app.db.models import User
from app.db.session import get_db
from app.schemas.case import (
    CaseCreateRequest,
    CaseDetailResponse,
    CaseListResponse,
    CaseUpdateRequest,
)
from app.schemas.case_decision import CaseDecisionRead, CaseDecisionRequest
from app.schemas.case_evidence import (
    CaseEvidenceAttachRequest,
    CaseEvidenceListResponse,
    CaseEvidenceRead,
)
from app.schemas.investigation import (
    InvestigationListResponse,
    InvestigationSummary,
    StartInvestigationResponse,
)
from app.services import cases as cases_service
from app.services import evidence as evidence_service
from app.services import investigations as investigations_service

router = APIRouter(prefix="/cases", tags=["cases"])

_ANALYST_PLUS = require_role("analyst", "senior_analyst", "admin")
_DECISION_MAKERS = require_role("senior_analyst", "admin")


@router.get("", response_model=CaseListResponse)
def list_cases(
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    assigned_to_user_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseListResponse:
    return cases_service.list_cases(
        db,
        status=status_filter,
        assigned_analyst_id=assigned_to_user_id,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CaseDetailResponse, status_code=status.HTTP_201_CREATED)
def create_case(
    body: CaseCreateRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> CaseDetailResponse:
    try:
        return cases_service.create_case(
            db, alert_ids=body.alert_ids, priority=body.priority, actor_user_id=user.id
        )
    except cases_service.AlertNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"alert(s) not found: {exc}"
        ) from exc


@router.get("/{case_id}", response_model=CaseDetailResponse)
def get_case(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> CaseDetailResponse:
    try:
        return cases_service.get_case(db, case_id)
    except cases_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc


@router.patch("/{case_id}", response_model=CaseDetailResponse)
def update_case(
    case_id: UUID,
    body: CaseUpdateRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> CaseDetailResponse:
    try:
        return cases_service.update_case(
            db, case_id, fields_set=body.model_dump(exclude_unset=True), actor_user_id=user.id
        )
    except cases_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    except cases_service.UserNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="assigned_analyst_id not found",
        ) from exc
    except cases_service.InvalidStatusTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid status transition: {exc}",
        ) from exc


@router.post(
    "/{case_id}/decision", response_model=CaseDecisionRead, status_code=status.HTTP_201_CREATED
)
def record_decision(
    case_id: UUID,
    body: CaseDecisionRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_DECISION_MAKERS)],
) -> CaseDecisionRead:
    """`senior_analyst`/`admin` only (docs/api-contracts.md §6) — the one
    endpoint in this system that may resolve a case, and it always
    requires an authenticated human and a rationale (CLAUDE.md
    human-in-the-loop rule).
    """
    try:
        return cases_service.record_decision(
            db,
            case_id,
            decision=body.decision,
            rationale=body.rationale,
            decided_by_user_id=user.id,
        )
    except cases_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    except cases_service.InvalidStatusTransition as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid status transition: {exc}",
        ) from exc


@router.get("/{case_id}/decision", response_model=CaseDecisionRead)
def get_case_decision(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> CaseDecisionRead:
    """So the case detail UI can re-display a recorded decision after a
    page reload — `POST .../decision`'s response alone doesn't persist
    across sessions client-side.
    """
    try:
        return cases_service.get_decision_for_case(db, case_id)
    except cases_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    except cases_service.DecisionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="no decision recorded for this case"
        ) from exc


@router.post(
    "/{case_id}/evidence", response_model=CaseEvidenceRead, status_code=status.HTTP_201_CREATED
)
def attach_evidence(
    case_id: UUID,
    body: CaseEvidenceAttachRequest,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> CaseEvidenceRead:
    try:
        return evidence_service.attach_evidence(db, case_id, body, actor_user_id=user.id)
    except evidence_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    except evidence_service.SourceRecordNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"source record not found: {exc}"
        ) from exc
    except evidence_service.InvalidEvidenceRequest as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/{case_id}/evidence", response_model=CaseEvidenceListResponse)
def list_case_evidence(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CaseEvidenceListResponse:
    """Lists what `POST /{case_id}/evidence` has attached so far — the
    case detail/investigation UI needs this to show the evidence trail
    without the client having to remember every id it ever attached.
    """
    try:
        rows, total = evidence_service.list_evidence_for_case(
            db, case_id, limit=limit, offset=offset
        )
    except evidence_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    return CaseEvidenceListResponse(
        items=[CaseEvidenceRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}/investigations", response_model=InvestigationListResponse)
def list_case_investigations(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    _user: Annotated[User, Depends(_ANALYST_PLUS)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvestigationListResponse:
    """Run-history summaries for a case's "Investigations" tab; full detail
    for one run is still `GET /investigations/{run_id}`.
    """
    try:
        rows, total = investigations_service.list_runs_for_case(
            db, case_id, limit=limit, offset=offset
        )
    except investigations_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    return InvestigationListResponse(
        items=[
            InvestigationSummary(
                run_id=r.id,
                case_id=r.case_id,
                started_by_user_id=r.started_by_user_id,
                status=r.status,  # type: ignore[arg-type]
                revision_count=r.revision_count,
                started_at=r.started_at,
                completed_at=r.completed_at,
            )
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{case_id}/investigations",
    response_model=StartInvestigationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_investigation(
    case_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[User, Depends(_ANALYST_PLUS)],
) -> StartInvestigationResponse:
    """Starts a LangGraph investigation run in the background and returns
    immediately (Part F: "should not block ordinary API requests
    indefinitely") — poll `GET /investigations/{run_id}` for progress.
    Always started by an authenticated human (never a service principal,
    never another agent); see `docs/agent-security.md`.
    """
    try:
        run = investigations_service.start_investigation(db, case_id, actor_user_id=user.id)
    except investigations_service.CaseNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="case not found") from exc
    except LLMProviderUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return StartInvestigationResponse(run_id=run.id, status=run.status)  # type: ignore[arg-type]
