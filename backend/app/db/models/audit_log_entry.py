import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLogEntry(Base):
    """Append-only audit trail (docs/database-design.md `audit_log_entries`;
    the Phase 5 brief calls this `audit_events` — same table, this
    codebase's existing name). Covers CLAUDE.md's "audit logging for
    authentication events, case decisions, and every agent run": `user_id`
    is null only for a system/service action (e.g. automated scoring);
    every human action — login, case decision, assignment, status change,
    evidence attach — has a real `user_id` from `get_current_user`.

    `entity_type`/`entity_id` is a generic polymorphic reference rather
    than a dedicated `case_id` column, so one table covers case-scoped
    events (`entity_type="case"`) *and* non-case events like `login` (no
    entity at all) *and* Phase 6's future `agent_run` events, without a
    column that's null for half of all rows. The attribute is named
    `event_metadata`, not `metadata` — `metadata` is reserved on every
    declarative model (it's `Base.metadata`); the column itself is still
    named `metadata` in Postgres.
    """

    __tablename__ = "audit_log_entries"
    __table_args__ = (
        Index("ix_audit_log_entries_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_log_entries_user_id", "user_id"),
        Index("ix_audit_log_entries_occurred_at", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
