"""app.accounts and app.transactions tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05

Creates the two operational tables PaySim ingestion writes to. No grants are
added here: migration 0001 already set `ALTER DEFAULT PRIVILEGES` for the
`app` schema (api_service gets SELECT/INSERT/UPDATE/DELETE, ml_trainer gets
SELECT) scoped to whatever role runs this migration (the admin/superuser) —
so tables created here automatically pick up the right grants.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_ref", sa.Text(), nullable=False),
        sa.Column("account_type", sa.Text(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("external_ref", name="uq_accounts_external_ref"),
        schema="app",
    )
    op.create_index(
        "ix_accounts_external_ref", "accounts", ["external_ref"], unique=False, schema="app"
    )

    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("external_ref", sa.Text(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("origin_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dest_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("origin_balance_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("origin_balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column("dest_balance_before", sa.Numeric(18, 2), nullable=False),
        sa.Column("dest_balance_after", sa.Numeric(18, 2), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["origin_account_id"],
            ["app.accounts.id"],
            name="fk_transactions_origin_account_id_accounts",
        ),
        sa.ForeignKeyConstraint(
            ["dest_account_id"],
            ["app.accounts.id"],
            name="fk_transactions_dest_account_id_accounts",
        ),
        sa.UniqueConstraint("external_ref", name="uq_transactions_external_ref"),
        schema="app",
    )
    op.create_index("ix_transactions_step", "transactions", ["step"], schema="app")
    op.create_index(
        "ix_transactions_origin_account_id_step",
        "transactions",
        ["origin_account_id", "step"],
        schema="app",
    )
    op.create_index(
        "ix_transactions_dest_account_id_step",
        "transactions",
        ["dest_account_id", "step"],
        schema="app",
    )


def downgrade() -> None:
    op.drop_table("transactions", schema="app")
    op.drop_table("accounts", schema="app")
