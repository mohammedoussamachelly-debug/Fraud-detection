import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Suggested statuses from the Phase 5 brief, stored lowercase to match this
# codebase's other status/type text columns (e.g. Alert.status). Valid
# transitions between them are a business rule, not a DB constraint — see
# `app/services/cases.py`'s `ALLOWED_STATUS_TRANSITIONS`.
CASE_STATUSES = ("open", "investigating", "pending_review", "resolved", "closed")
CASE_PRIORITIES = ("low", "medium", "high", "critical")


class Case(Base):
    """An investigation grouping one or more alerts. Per CLAUDE.md's
    human-in-the-loop rule, no code path may set `status="resolved"`
    without a corresponding `CaseDecision` row — see
    `app/services/cases.py::record_decision`, the only function that makes
    that transition.
    """

    __tablename__ = "cases"
    __table_args__ = (
        CheckConstraint(f"status IN {CASE_STATUSES!r}", name="ck_cases_status"),
        CheckConstraint(f"priority IN {CASE_PRIORITIES!r}", name="ck_cases_priority"),
        Index("ix_cases_status", "status"),
        Index("ix_cases_assigned_analyst_id", "assigned_analyst_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    priority: Mapped[str] = mapped_column(Text, nullable=False, server_default="medium")
    assigned_analyst_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseAlert(Base):
    """Join table: a case aggregates one or more alerts (docs/database-design.md
    `case_alerts`). `linked_at` isn't in the Phase 5 brief's literal column
    list but is needed to order "what was attached when" in the case detail
    view and audit trail — trivial to keep and otherwise unrecoverable.
    """

    __tablename__ = "case_alerts"

    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.cases.id"), primary_key=True
    )
    alert_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.alerts.id"), primary_key=True
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
