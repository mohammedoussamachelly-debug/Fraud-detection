"""Password hashing and JWT issuance/verification for human sessions
(analyst/senior_analyst/admin — docs/api-contracts.md §0). The `service`
machine principal does not go through here at all; it's checked directly
against `settings.service_api_key` (see `app/api/deps.py`), since it isn't
a user row and never carries case-decision rights.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(*, subject: str, role: str) -> tuple[str, int]:
    """Returns `(token, expires_in_seconds)`. `subject` is the user id
    (string form of the UUID); `role` is embedded so route dependencies can
    check it without a DB round trip, but `get_current_user` still loads the
    user row to catch a deactivated account immediately (§6: "no anonymous
    privileged actions" also means no privileged actions on a revoked one).
    """
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


class InvalidToken(Exception):
    pass


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
