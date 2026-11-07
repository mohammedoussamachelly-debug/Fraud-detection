import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import get_settings

logger = logging.getLogger("sentinelai")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="SentinelAI API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Matches the problem+json error shape documented in
        # docs/api-contracts.md §0.
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": "https://sentinelai.dev/errors/validation-error",
                "title": "Validation error",
                "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "detail": jsonable_encoder(exc.errors()),
                "instance": str(request.url.path),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # A genuine, unexpected failure (e.g. inference blew up) is reported
        # as a 500 problem+json — never swallowed into a fabricated result.
        logger.exception("Unhandled exception while serving %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": "https://sentinelai.dev/errors/internal-error",
                "title": "Internal server error",
                "status": 500,
                "detail": "An unexpected error occurred.",
                "instance": str(request.url.path),
            },
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
