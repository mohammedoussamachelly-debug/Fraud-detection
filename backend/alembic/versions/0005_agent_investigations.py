"""agent_runs, agent_steps, agent_evidence_refs

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-08

Phase 6: LangGraph investigation workflow persistence — see
docs/multi-agent-architecture.md. All tables are in the `app` schema;
none reference `ground_truth` by FK or column. No grants are added here:
migration 0001's `ALTER DEFAULT PRIVILEGES` on `app` already covers
tables created after it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

AGENT_RUN_STATUSES = (
    "running",
    "awaiting_approval",
    "approved",
    "rejected",
    "revision_requested",
    "failed",
)
NODE_NAMES = (
    "intake",
    "evidence_collector",
    "network_investigator",
    "report_writer",
    "human_approval_gate",
)
STEP_STATUSES = ("succeeded", "failed")
AGENT_EVIDENCE_TYPES = (
    "transaction",
    "risk_score",
    "shap_explanation",
    "network_finding",
    "historical_stats",
    "similar_case",
)


def _ts_col(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="running"),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column(
            "tool_versions",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("revision_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "review_feedback",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("draft_report", postgresql.JSONB(), nullable=True),
        sa.Column("final_report", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        _ts_col("started_at"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["case_id"], ["app.cases.id"], name="fk_agent_runs_case_id_cases"),
        sa.ForeignKeyConstraint(
            ["started_by_user_id"], ["app.users.id"], name="fk_agent_runs_started_by_user_id_users"
        ),
        sa.CheckConstraint(f"status IN {AGENT_RUN_STATUSES!r}", name="ck_agent_runs_status"),
        schema="app",
    )
    op.create_index("ix_agent_runs_case_id", "agent_runs", ["case_id"], schema="app")
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"], schema="app")

    op.create_table(
        "agent_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("node_name", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "tool_calls", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("output", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        _ts_col("started_at"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["agent_run_id"], ["app.agent_runs.id"], name="fk_agent_steps_agent_run_id_agent_runs"
        ),
        sa.CheckConstraint(f"node_name IN {NODE_NAMES!r}", name="ck_agent_steps_node_name"),
        sa.CheckConstraint(f"status IN {STEP_STATUSES!r}", name="ck_agent_steps_status"),
        schema="app",
    )
    op.create_index("ix_agent_steps_agent_run_id", "agent_steps", ["agent_run_id"], schema="app")

    op.create_table(
        "agent_evidence_refs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("collected_by_node", sa.Text(), nullable=False),
        _ts_col("created_at"),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["app.agent_runs.id"],
            name="fk_agent_evidence_refs_agent_run_id_agent_runs",
        ),
        sa.CheckConstraint(
            f"evidence_type IN {AGENT_EVIDENCE_TYPES!r}",
            name="ck_agent_evidence_refs_evidence_type",
        ),
        schema="app",
    )
    op.create_index(
        "ix_agent_evidence_refs_agent_run_id", "agent_evidence_refs", ["agent_run_id"], schema="app"
    )


def downgrade() -> None:
    op.drop_table("agent_evidence_refs", schema="app")
    op.drop_table("agent_steps", schema="app")
    op.drop_table("agent_runs", schema="app")
