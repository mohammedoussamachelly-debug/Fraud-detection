from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import ServicePrincipal, require_service
from app.core.config import get_settings
from app.db.session import get_db
from app.ml.inference import ModelArtifactUnavailable, load_active_artifact
from app.schemas.risk_score_record import RiskScorePersistRequest, RiskScorePersistResponse
from app.services.scoring_persistence import TransactionNotFound, persist_risk_score

router = APIRouter(prefix="/risk-scores", tags=["risk-scores"])


@router.post("", response_model=RiskScorePersistResponse)
def create_risk_score(
    request: RiskScorePersistRequest,
    http_request: Request,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[ServicePrincipal, Depends(require_service)],
) -> RiskScorePersistResponse | JSONResponse:
    """`service`-role only (docs/api-contracts.md §0) — called by the
    scoring/alerting job, same principal as `/transactions/ingest`. Not an
    analyst action, so it carries no case-decision rights and is audited
    with `user_id=None` (system action) in `app/services/scoring_persistence.py`.
    """
    settings = get_settings()
    try:
        artifact = load_active_artifact(settings.ml_artifacts_dir)
    except ModelArtifactUnavailable as exc:
        return JSONResponse(
            status_code=503,
            content={
                "type": "https://sentinelai.dev/errors/model-unavailable",
                "title": "Model unavailable",
                "status": 503,
                "detail": str(exc),
                "instance": str(http_request.url.path),
            },
        )

    try:
        return persist_risk_score(
            db,
            artifact,
            request.transaction_id,
            include_explanation=request.include_explanation,
            actor_user_id=None,
        )
    except TransactionNotFound:
        return JSONResponse(
            status_code=404,
            content={
                "type": "https://sentinelai.dev/errors/not-found",
                "title": "Not found",
                "status": 404,
                "detail": "transaction not found",
                "instance": str(http_request.url.path),
            },
        )
