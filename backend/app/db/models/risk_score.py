import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RiskScore(Base):
    """A persisted scoring result for one transaction (Phase 5 — scoring
    itself, via `app/ml/inference.py`, is unchanged from Phase 3; this table
    just records the result so alerts/cases/evidence can reference a real
    row instead of re-scoring on every read).

    `model_version` is the artifact's `version_label` string (same value
    `POST /risk/score` already returns, see `app/ml/inference.py`) — not a
    FK to a `model_versions` table, matching the existing inference
    convention rather than introducing a table this codebase doesn't have.

    Unique on `(transaction_id, model_version)`: scoring the same
    transaction again with the same active model version is idempotent —
    the existing row is returned, never duplicated (§3 "Idempotency").
    Scoring it again after the active model version changes creates a new
    row, since a different model's score is a different, independently
    meaningful fact (§3 "Correct behavior across model versions").
    """

    __tablename__ = "risk_scores"
    __table_args__ = (
        UniqueConstraint(
            "transaction_id", "model_version", name="uq_risk_scores_transaction_id_model_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app.transactions.id"), nullable=False, index=True
    )
    risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    risk_level: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    threshold_used: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    # Explanation contributions from app/ml/inference.explain, captured at
    # scoring time so later evidence attachment never has to reload a
    # possibly-rotated model artifact to reproduce it. Null if the scoring
    # request didn't ask for an explanation.
    shap_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
