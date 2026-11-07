import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DECISION_VALUES = ("confirmed_fraud", "not_fraud", "dismissed")


class CaseDecision(Base):
    """The human-in-the-loop record (docs/database-design.md `case_decisions`).

    Not in the Phase 5 brief's §2 table list, but added anyway: CLAUDE.md's
    Security Rules are explicit and non-negotiable — "no code path marks a
    case resolved, confirmed-fraud, or dismissed without a recorded
    analyst/approver decision" — and the brief's own §5/§6 ask for exactly
    this ("resolve cases through authorized human actions", "no AI agent or
    unauthenticated client approves consequential decisions"). A `Case.status`
    flip to "resolved" with no accountable row behind it would violate that
    rule, so this table is the mechanism, not an addition beyond scope.

    `decided_by_user_id` is NOT NULL — every decision has an accountable
    human (never a service-principal action; see `app/api/deps.py`).
    """

    __tablename__ = "case_decisions"
    __table_args__ = (
        CheckConstraint(f"decision IN {DECISION_VALUES!r}", name="ck_case_decisions_decision"),
        Index("ix_case_decisions_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.cases.id"), nullable=False
    )
    decided_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=False
    )
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
