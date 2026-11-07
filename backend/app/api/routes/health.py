from fastapi import APIRouter, Response, status

from app.db.session import check_database_connection
from app.schemas.health import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness probe: process is up. Does not touch the database."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness(response: Response) -> ReadinessResponse:
    """Readiness probe: process is up AND the database is reachable."""
    if check_database_connection():
        return ReadinessResponse(status="ready", database="connected")

    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="not_ready", database="unreachable")
