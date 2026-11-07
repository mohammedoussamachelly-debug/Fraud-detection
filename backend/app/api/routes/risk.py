from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import ServicePrincipal, require_service
from app.core.config import get_settings
from app.db.session import get_db
from app.ml.inference import ModelArtifactUnavailable, load_active_artifact
from app.schemas.risk import RiskScoreRequest, RiskScoreResponse
from app.services.risk_scoring import score_transaction

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/score", response_model=RiskScoreResponse)
def score(
    request: RiskScoreRequest,
    http_request: Request,
    db: Annotated[Session, Depends(get_db)],
    _principal: Annotated[ServicePrincipal, Depends(require_service)],
) -> RiskScoreResponse | JSONResponse:
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

    return score_transaction(db, artifact, request)
