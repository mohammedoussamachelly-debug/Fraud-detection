import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# docs/api-contracts.md §0: `service` is a fourth principal but is a machine
# credential checked against `settings.service_api_key` (app/api/deps.py),
# never a row in this table.
USER_ROLES = ("analyst", "senior_analyst", "admin")


class User(Base):
    """An authenticated human (Phase 5). Role gates case-decision and
    audit-log access — see `app/api/deps.py`. No password is ever stored or
    logged in plaintext; only `password_hash` (bcrypt, `app/core/security.py`).
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(f"role IN {USER_ROLES!r}", name="ck_users_role"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
