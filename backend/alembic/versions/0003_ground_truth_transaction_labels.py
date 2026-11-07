"""ground_truth.transaction_labels table

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05

Isolated label table — see docs/database-design.md §3. Deliberately created
with plain `op.create_table` (no ORM model in `backend/app`, which only ever
maps the `app` schema) so there is nothing in the running API process that
could accidentally import or query this table. `ml_trainer` picks up SELECT
automatically via the `ALTER DEFAULT PRIVILEGES` set in migration 0001.
`api_service` has no USAGE on the `ground_truth` schema at all (also from
migration 0001), so it cannot reach this table regardless of grants on it.

No FK to `app.transactions.id`: the schemas are joined only by
`external_ref` value, never by a foreign key, so no ORM relationship can
traverse from `app` into `ground_truth` even by accident.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transaction_labels",
        sa.Column("transaction_external_ref", sa.Text(), primary_key=True),
        sa.Column("is_fraud", sa.Boolean(), nullable=False),
        sa.Column("is_flagged_fraud", sa.Boolean(), nullable=False),
        sa.Column(
            "loaded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        schema="ground_truth",
    )


def downgrade() -> None:
    op.drop_table("transaction_labels", schema="ground_truth")
