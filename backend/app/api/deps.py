"""Auth dependencies shared by every Phase 5 route. Two principals, per
docs/api-contracts.md §0:

- a human (`User` row, role `analyst`/`senior_analyst`/`admin`), authenticated
  with a JWT from `POST /auth/login` (`app/core/security.py`).
- `service`, a machine credential checked directly against
  `settings.service_api_key` (constant-time compare) — never a `User` row,
  never case-decision rights (`require_role` only ever receives a `User`).

Both arrive as `Authorization: Bearer <token>`; `get_current_principal`
tells them apart by trying the service key first (a fixed string compare)
before attempting JWT decode.
"""

import secrets
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import InvalidToken, decode_access_token
from app.db.models import User
from app.db.session import get_db

_bearer = HTTPBearer(auto_error=False)


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _require_credentials(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise _unauthorized("missing bearer token")
    return credentials.credentials


def get_current_user(
    token: Annotated[str, Depends(_require_credentials)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    try:
        payload = decode_access_token(token)
    except InvalidToken as exc:
        raise _unauthorized("invalid or expired token") from exc

    user = db.get(User, UUID(payload["sub"]))
    if user is None or not user.is_active:
        raise _unauthorized("user not found or deactivated")
    return user


def require_role(*allowed_roles: str):  # noqa: ANN201  (returns a FastAPI dependency callable)
    """`analyst+` in the docs means "analyst, senior_analyst, or admin" —
    callers pass every role allowed, not just the minimum one, so the
    dependency never has to encode a role ordering.
    """

    def _dependency(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires one of roles: {', '.join(allowed_roles)}",
            )
        return user

    return _dependency


@dataclass
class ServicePrincipal:
    kind: str = "service"


def require_service(token: Annotated[str, Depends(_require_credentials)]) -> ServicePrincipal:
    settings = get_settings()
    if not secrets.compare_digest(token, settings.service_api_key):
        raise _unauthorized("invalid service credential")
    return ServicePrincipal()
