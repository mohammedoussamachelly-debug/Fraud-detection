import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    """A single ingested transaction (PaySim row). `step` is the sole ordering
    key for "what happened before what" — see docs/database-design.md §4.
    `origin_balance_before`/`dest_balance_before` are the PRE-transaction
    balances (PaySim `oldbalanceOrg`/`oldbalanceDest`): safe to use as model
    features for scoring this transaction. The `_after` balances are
    POST-transaction and must never be used to score this same transaction.

    No `is_fraud` column exists here by design — see docs/database-design.md §3.
    """

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("external_ref", name="uq_transactions_external_ref"),
        Index("ix_transactions_step", "step"),
        Index("ix_transactions_origin_account_id_step", "origin_account_id", "step"),
        Index("ix_transactions_dest_account_id_step", "dest_account_id", "step"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    step: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    origin_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    dest_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    origin_balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    origin_balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    dest_balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    dest_balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
