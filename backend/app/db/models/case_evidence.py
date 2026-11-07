import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# "analyst_note" is how §5's "add investigation notes" is represented: a
# note is evidence of the analyst's own reasoning, stored the same way as
# every other evidence type rather than a second, parallel notes table the
# Phase 5 brief's §2 table list doesn't ask for. It's the one evidence_type
# `app/services/evidence.py` lets the client supply free text for — every
# other type is always a server-resolved snapshot of a real record (§7
# "do not fabricate evidence").
EVIDENCE_TYPES = (
    "transaction",
    "risk_score",
    "shap_explanation",
    "graph_neighborhood",
    "graph_metrics",
    "fund_flow",
    "historical_stats",
    "analyst_note",
)


class CaseEvidence(Base):
    """A snapshot of one piece of evidence attached to a case.

    `evidence_payload` is always a server-computed/validated snapshot taken
    at attach time (point-in-time, matching docs/database-design.md §4's
    "no stored aggregate claims anything about the future") — never
    client-supplied free-form JSON — except for `evidence_type ==
    "analyst_note"`, where the payload *is* the analyst's own text. See
    `app/services/evidence.py` for how each type is resolved and validated
    against the real source record before being persisted.
    """

    __tablename__ = "case_evidence"
    __table_args__ = (
        CheckConstraint(
            f"evidence_type IN {EVIDENCE_TYPES!r}", name="ck_case_evidence_evidence_type"
        ),
        Index("ix_case_evidence_case_id", "case_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.cases.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    # "<table>:<uuid>" — the same `type:uuid` convention docs/api-contracts.md
    # §6.1 already uses for agent report `evidence_refs`, so this schema is
    # ready to interoperate with Phase 6's evidence-citation format.
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
