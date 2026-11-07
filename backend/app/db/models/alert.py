import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

ALERT_TYPES = ("model_threshold", "graph_structural", "manual")
ALERT_SEVERITIES = ("low", "medium", "high", "critical")
ALERT_STATUSES = ("open", "triaged", "escalated", "dismissed")


class Alert(Base):
    """A fraud alert on one transaction. `risk_score_id` is nullable because
    an alert can originate from a graph-structural rule or a manual flag
    (`alert_type`) with no risk-scoring row behind it at all — see
    docs/database-design.md's `alerts` design, which this follows.

    Unique on `(transaction_id, alert_type)`: re-scoring (or re-evaluating
    the same graph rule for) the same transaction never creates a second
    alert of the same type — the existing one is returned instead
    (§4 "Duplicate-alert prevention").

    Per CLAUDE.md and §4: this table records that a transaction crossed a
    configured review threshold — it never asserts the transaction *is*
    fraud. `status`/`severity` are triage state, not a verdict; only a
    `CaseDecision` (recorded by a senior_analyst/admin) is that.
    """

    __tablename__ = "alerts"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "alert_type", name="uq_alerts_transaction_id_alert_type"
        ),
        CheckConstraint(f"alert_type IN {ALERT_TYPES!r}", name="ck_alerts_alert_type"),
        CheckConstraint(f"severity IN {ALERT_SEVERITIES!r}", name="ck_alerts_severity"),
        CheckConstraint(f"status IN {ALERT_STATUSES!r}", name="ck_alerts_status"),
        Index("ix_alerts_status", "status"),
        Index("ix_alerts_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.transactions.id"), nullable=False, index=True
    )
    risk_score_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.risk_scores.id"), nullable=True
    )
    alert_type: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
