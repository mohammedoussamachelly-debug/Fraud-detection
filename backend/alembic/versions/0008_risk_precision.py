"""Preserve genuine small probabilities instead of rounding them to zero."""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("risk_score", "threshold_used"):
        op.alter_column(
            "risk_scores",
            column,
            schema="app",
            type_=sa.Numeric(16, 15),
            existing_type=sa.Numeric(6, 5),
            existing_nullable=False,
        )


def downgrade():
    for column in ("risk_score", "threshold_used"):
        op.alter_column(
            "risk_scores",
            column,
            schema="app",
            type_=sa.Numeric(6, 5),
            existing_type=sa.Numeric(16, 15),
            existing_nullable=False,
        )
