"""Isolated synthetic demo batch ownership; no changes to operational records."""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_batches",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(), nullable=False),
        sa.Column("scenarios", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema="app",
    )
    op.create_table(
        "demo_records",
        sa.Column("batch_id", sa.Text(), sa.ForeignKey("app.demo_batches.id"), primary_key=True),
        sa.Column("entity_type", sa.Text(), primary_key=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), primary_key=True),
        schema="app",
    )
    op.create_index(
        "ix_demo_records_entity",
        "demo_records",
        ["entity_type", "entity_id"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("demo_records", schema="app")
    op.drop_table("demo_batches", schema="app")
