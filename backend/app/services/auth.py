from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, verify_password
from app.db.models import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import audit


class InvalidCredentials(Exception):
    pass


def login(db: Session, request: LoginRequest) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == request.email))
    # Same error for "no such user" and "wrong password" — doesn't reveal
    # which, so a caller can't enumerate valid emails via this endpoint.
    if user is None or not user.is_active:
        raise InvalidCredentials("invalid email or password")
    if not verify_password(request.password, user.password_hash):
        raise InvalidCredentials("invalid email or password")

    token, expires_in = create_access_token(subject=str(user.id), role=user.role)
    audit.record_event(
        db, user_id=user.id, action="login", entity_type="user", entity_id=user.id, metadata={}
    )
    db.commit()
    return TokenResponse(access_token=token, expires_in=expires_in)
