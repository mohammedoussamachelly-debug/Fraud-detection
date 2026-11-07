import uuid
from datetime import datetime

from sqlalchemy import DateTime, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Account(Base):
    """An account observed in ingested transactions (PaySim `nameOrig`/`nameDest`).

    No fraud signal lives here — see docs/database-design.md §3. `account_type`
    is derived purely from PaySim's naming convention (`C...` = customer,
    `M...` = merchant), never from a fraud label.
    """

    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("external_ref", name="uq_accounts_external_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    account_type: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
