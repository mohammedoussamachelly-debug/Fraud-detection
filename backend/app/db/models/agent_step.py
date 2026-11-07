import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

NODE_NAMES = (
    "intake",
    "evidence_collector",
    "network_investigator",
    "report_writer",
    "human_approval_gate",
)
STEP_STATUSES = ("succeeded", "failed")


class AgentStep(Base):
    """One execution of one LangGraph node, one row per attempt (so a
    retried node leaves a full attempt history, not just the final try —
    append-only, per CLAUDE.md's audit-logging rule and Part D's
    "maintain append-only auditability for important execution events").

    `tool_calls` is this run's "tool-call metadata" (Part D): a list of
    `{tool, args_summary, result_ref, duration_ms}` — reference ids and
    short summaries only, never a raw sensitive payload or secret (Part D:
    "avoid storing unnecessary sensitive data or secrets in model
    traces"); there is no PII in this synthetic system, but tokens/keys
    are never logged here regardless.
    """

    __tablename__ = "agent_steps"
    __table_args__ = (
        CheckConstraint(f"node_name IN {NODE_NAMES!r}", name="ck_agent_steps_node_name"),
        CheckConstraint(f"status IN {STEP_STATUSES!r}", name="ck_agent_steps_status"),
        Index("ix_agent_steps_agent_run_id", "agent_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.agent_runs.id"), nullable=False
    )
    node_name: Mapped[str] = mapped_column(Text, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="'[]'::jsonb")
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
