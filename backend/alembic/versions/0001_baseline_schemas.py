"""baseline schemas, least-privilege roles, and ground-truth isolation grants

Revision ID: 0001
Revises:
Create Date: 2026-11-04

This migration must run as the Postgres admin/superuser (ALEMBIC_DATABASE_URL),
never as api_service or ml_trainer — those roles are what it creates. It
implements the access-control design in docs/database-design.md §3: the
api_service role (used by the running backend, including agent tool calls once
they exist) gets full read/write on the `app` schema and an explicit REVOKE on
`ground_truth`; ml_trainer (used only by the offline ml/ training pipeline, not
yet implemented) gets read-only access to both.
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _escape_literal(value: str) -> str:
    return value.replace("'", "''")


def _create_role_if_missing(role_name: str, password_env_var: str, default_password: str) -> None:
    password = _escape_literal(os.environ.get(password_env_var, default_password))
    op.execute(
        sa.text(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '{role_name}') THEN
                    CREATE ROLE {role_name} LOGIN PASSWORD '{password}';
                END IF;
            END
            $$;
            """
        )
    )


def upgrade() -> None:
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS app"))
    op.execute(sa.text("CREATE SCHEMA IF NOT EXISTS ground_truth"))

    _create_role_if_missing("api_service", "API_SERVICE_DB_PASSWORD", "api_service_dev_password")
    _create_role_if_missing("ml_trainer", "ML_TRAINER_DB_PASSWORD", "ml_trainer_dev_password")

    # api_service: full read/write on `app`. No grant at all on `ground_truth` —
    # this is an explicit REVOKE, not merely "never granted", so it holds even
    # if a future migration adds a broader default grant by mistake.
    op.execute(sa.text("GRANT USAGE ON SCHEMA app TO api_service"))
    op.execute(
        sa.text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO api_service")
    )
    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA app "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO api_service"
        )
    )
    op.execute(sa.text("REVOKE ALL ON SCHEMA ground_truth FROM api_service"))
    op.execute(sa.text("REVOKE ALL ON ALL TABLES IN SCHEMA ground_truth FROM api_service"))

    # ml_trainer: read-only on `app` (features) and `ground_truth` (labels).
    # Never granted write access anywhere.
    op.execute(sa.text("GRANT USAGE ON SCHEMA app TO ml_trainer"))
    op.execute(sa.text("GRANT SELECT ON ALL TABLES IN SCHEMA app TO ml_trainer"))
    op.execute(
        sa.text("ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO ml_trainer")
    )
    op.execute(sa.text("GRANT USAGE ON SCHEMA ground_truth TO ml_trainer"))
    op.execute(sa.text("GRANT SELECT ON ALL TABLES IN SCHEMA ground_truth TO ml_trainer"))
    op.execute(
        sa.text(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA ground_truth GRANT SELECT ON TABLES TO ml_trainer"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("REVOKE ALL ON SCHEMA ground_truth FROM ml_trainer"))
    op.execute(sa.text("REVOKE ALL ON SCHEMA app FROM ml_trainer"))
    op.execute(sa.text("REVOKE ALL ON SCHEMA app FROM api_service"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS ground_truth CASCADE"))
    op.execute(sa.text("DROP SCHEMA IF EXISTS app CASCADE"))
    # Roles are intentionally not dropped: a role can own objects in other
    # databases or have active connections, and DROP ROLE fails loudly in
    # those cases. Removing api_service/ml_trainer is a deliberate, separate
    # operational action, not an automatic part of this migration's rollback.
