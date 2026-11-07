"""Ownership registry for explicitly synthetic, safely resettable demo batches."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemoBatch(Base):
    __tablename__ = "demo_batches"
    id: Mapped[str] = mapped_column(Text, primary_key=True)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scenarios: Mapped[list] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")


class DemoRecord(Base):
    __tablename__ = "demo_records"
    batch_id: Mapped[str] = mapped_column(ForeignKey("app.demo_batches.id"), primary_key=True)
    entity_type: Mapped[str] = mapped_column(Text, primary_key=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
