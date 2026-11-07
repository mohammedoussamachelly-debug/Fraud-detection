import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# A superset of `app.db.models.case_evidence.EVIDENCE_TYPES`: agent runs
# also produce "network_finding" (a structural pattern from the graph
# module) and "similar_case" (a past case decision) references, which
# aren't individually attachable as case_evidence types but are exactly
# what docs/api-contracts.md §6.2's `get_graph_neighborhood`/
# `get_similar_past_cases` tools return.
AGENT_EVIDENCE_TYPES = (
    "transaction",
    "risk_score",
    "shap_explanation",
    "network_finding",
    "historical_stats",
    "similar_case",
)


class AgentEvidenceRef(Base):
    """A reference to one real record an agent retrieved and cited while
    producing a report — the structural backbone of "validate every
    evidence reference against actual stored records" (Part E) and
    "every hypothesis must cite a real evidence reference or be dropped"
    (docs/architecture.md §7's HypothesisSynthesis rule). `source_reference`
    follows the same `"<table>:<uuid>"` convention as `case_evidence`
    (docs/alerts-and-cases.md §5) and the agent-report citation format
    already sketched in docs/api-contracts.md §6.1.

    No `evidence_payload` column here, unlike `case_evidence`: this table
    is the agent's own working citation list for one run, not a human
    attaching evidence to a case — the *content* an analyst wants to keep
    is the final/draft report's prose plus these references, which can be
    re-resolved on demand (`GET /investigations/{run_id}`) since they
    always point at a real, still-queryable `app` row.
    """

    __tablename__ = "agent_evidence_refs"
    __table_args__ = (
        CheckConstraint(
            f"evidence_type IN {AGENT_EVIDENCE_TYPES!r}",
            name="ck_agent_evidence_refs_evidence_type",
        ),
        Index("ix_agent_evidence_refs_agent_run_id", "agent_run_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.agent_runs.id"), nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    collected_by_node: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
