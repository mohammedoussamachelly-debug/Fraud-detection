import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# docs/architecture.md §7.1's workflow states, collapsed to what this table
# actually needs to track (Intake/EvidenceRetrieval/NetworkInvestigation/
# ReportDraft are sub-steps recorded in `agent_steps`, not run-level
# statuses): a run is `running` until the report is drafted, then sits at
# `awaiting_approval` until a human calls approve/reject/request-revision.
AGENT_RUN_STATUSES = (
    "running",
    "awaiting_approval",
    "approved",
    "rejected",
    "revision_requested",
    "failed",
)

# Bounded per Part C ("do not create unnecessary autonomous loops") — after
# this many `request-revision` round trips, the run must be approved or
# rejected; it cannot cycle forever.
MAX_REVISION_ROUNDS = 3


class AgentRun(Base):
    """One LangGraph investigation run on a case (Phase 6). Always started
    by an authenticated human (`started_by_user_id` NOT NULL — an agent
    never starts its own investigation); never resolves the case itself —
    see `app/services/investigations.py` and `docs/agent-security.md`.

    `model_provider`/`model_name`/`prompt_version`/`tool_versions` are the
    traceability fields Part E requires ("record model name, prompt
    version, tool versions, execution time, and run identifiers") so a
    later audit can reproduce exactly what produced a given report.
    `draft_report` is populated as soon as the ReportWriter agent
    finishes; `final_report` is populated **only** once a human approves
    (matching docs/database-design.md §2's original `agent_runs` sketch:
    "final_report jsonb, nullable, only populated once approved").
    """

    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(f"status IN {AGENT_RUN_STATUSES!r}", name="ck_agent_runs_status"),
        Index("ix_agent_runs_case_id", "case_id"),
        Index("ix_agent_runs_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.cases.id"), nullable=False
    )
    started_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.users.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    model_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    tool_versions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="'{}'::jsonb")
    revision_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    review_feedback: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )
    draft_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    final_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
