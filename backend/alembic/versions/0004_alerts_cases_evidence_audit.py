"""users, risk_scores, alerts, cases, case_alerts, case_decisions,
case_evidence, audit_log_entries

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-07

Phase 5: persistent risk scores, fraud alerts, investigation cases,
evidence, and audit logging — see docs/alerts-and-cases.md and
docs/authentication.md. All tables are in the `app` schema; none of them
reference `ground_truth` by FK or by column (docs/database-design.md §3
holds unchanged — `api_service` still has no grant on that schema at all).
No grants are added here: migration 0001's `ALTER DEFAULT PRIVILEGES` on
`app` already covers tables created after it, same as migration 0002.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

USER_ROLES = ("analyst", "senior_analyst", "admin")
ALERT_TYPES = ("model_threshold", "graph_structural", "manual")
ALERT_SEVERITIES = ("low", "medium", "high", "critical")
ALERT_STATUSES = ("open", "triaged", "escalated", "dismissed")
CASE_STATUSES = ("open", "investigating", "pending_review", "resolved", "closed")
CASE_PRIORITIES = ("low", "medium", "high", "critical")
DECISION_VALUES = ("confirmed_fraud", "not_fraud", "dismissed")
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


def _ts_col(name: str) -> sa.Column:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        _ts_col("created_at"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(f"role IN {USER_ROLES!r}", name="ck_users_role"),
        schema="app",
    )
    op.create_index("ix_users_email", "users", ["email"], schema="app")

    op.create_table(
        "risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_score", sa.Numeric(6, 5), nullable=False),
        sa.Column("risk_level", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("threshold_used", sa.Numeric(6, 5), nullable=False),
        sa.Column("shap_values", postgresql.JSONB(), nullable=True),
        _ts_col("scored_at"),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["app.transactions.id"],
            name="fk_risk_scores_transaction_id_transactions",
        ),
        sa.UniqueConstraint(
            "transaction_id", "model_version", name="uq_risk_scores_transaction_id_model_version"
        ),
        schema="app",
    )
    op.create_index(
        "ix_risk_scores_transaction_id", "risk_scores", ["transaction_id"], schema="app"
    )

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("risk_score_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        _ts_col("created_at"),
        sa.ForeignKeyConstraint(
            ["transaction_id"],
            ["app.transactions.id"],
            name="fk_alerts_transaction_id_transactions",
        ),
        sa.ForeignKeyConstraint(
            ["risk_score_id"], ["app.risk_scores.id"], name="fk_alerts_risk_score_id_risk_scores"
        ),
        sa.UniqueConstraint(
            "transaction_id", "alert_type", name="uq_alerts_transaction_id_alert_type"
        ),
        sa.CheckConstraint(f"alert_type IN {ALERT_TYPES!r}", name="ck_alerts_alert_type"),
        sa.CheckConstraint(f"severity IN {ALERT_SEVERITIES!r}", name="ck_alerts_severity"),
        sa.CheckConstraint(f"status IN {ALERT_STATUSES!r}", name="ck_alerts_status"),
        schema="app",
    )
    op.create_index("ix_alerts_transaction_id", "alerts", ["transaction_id"], schema="app")
    op.create_index("ix_alerts_status", "alerts", ["status"], schema="app")
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"], schema="app")

    op.create_table(
        "cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("priority", sa.Text(), nullable=False, server_default="medium"),
        sa.Column("assigned_analyst_id", postgresql.UUID(as_uuid=True), nullable=True),
        _ts_col("created_at"),
        _ts_col("updated_at"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_analyst_id"], ["app.users.id"], name="fk_cases_assigned_analyst_id_users"
        ),
        sa.CheckConstraint(f"status IN {CASE_STATUSES!r}", name="ck_cases_status"),
        sa.CheckConstraint(f"priority IN {CASE_PRIORITIES!r}", name="ck_cases_priority"),
        schema="app",
    )
    op.create_index("ix_cases_status", "cases", ["status"], schema="app")
    op.create_index("ix_cases_assigned_analyst_id", "cases", ["assigned_analyst_id"], schema="app")

    op.create_table(
        "case_alerts",
        sa.Column("case_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), primary_key=True),
        _ts_col("linked_at"),
        sa.ForeignKeyConstraint(["case_id"], ["app.cases.id"], name="fk_case_alerts_case_id_cases"),
        sa.ForeignKeyConstraint(
            ["alert_id"], ["app.alerts.id"], name="fk_case_alerts_alert_id_alerts"
        ),
        schema="app",
    )
    op.create_index("ix_case_alerts_alert_id", "case_alerts", ["alert_id"], schema="app")

    op.create_table(
        "case_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        _ts_col("decided_at"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["app.cases.id"], name="fk_case_decisions_case_id_cases"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["app.users.id"],
            name="fk_case_decisions_decided_by_user_id_users",
        ),
        sa.CheckConstraint(f"decision IN {DECISION_VALUES!r}", name="ck_case_decisions_decision"),
        schema="app",
    )
    op.create_index("ix_case_decisions_case_id", "case_decisions", ["case_id"], schema="app")

    op.create_table(
        "case_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.Text(), nullable=False),
        sa.Column("source_reference", sa.Text(), nullable=False),
        sa.Column("evidence_payload", postgresql.JSONB(), nullable=False),
        _ts_col("created_at"),
        sa.ForeignKeyConstraint(
            ["case_id"], ["app.cases.id"], name="fk_case_evidence_case_id_cases"
        ),
        sa.CheckConstraint(
            f"evidence_type IN {EVIDENCE_TYPES!r}", name="ck_case_evidence_evidence_type"
        ),
        schema="app",
    )
    op.create_index("ix_case_evidence_case_id", "case_evidence", ["case_id"], schema="app")

    op.create_table(
        "audit_log_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        _ts_col("occurred_at"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["app.users.id"], name="fk_audit_log_entries_user_id_users"
        ),
        schema="app",
    )
    op.create_index(
        "ix_audit_log_entries_entity_type_entity_id",
        "audit_log_entries",
        ["entity_type", "entity_id"],
        schema="app",
    )
    op.create_index("ix_audit_log_entries_user_id", "audit_log_entries", ["user_id"], schema="app")
    op.create_index(
        "ix_audit_log_entries_occurred_at", "audit_log_entries", ["occurred_at"], schema="app"
    )


def downgrade() -> None:
    op.drop_table("audit_log_entries", schema="app")
    op.drop_table("case_evidence", schema="app")
    op.drop_table("case_decisions", schema="app")
    op.drop_table("case_alerts", schema="app")
    op.drop_table("cases", schema="app")
    op.drop_table("alerts", schema="app")
    op.drop_table("risk_scores", schema="app")
    op.drop_table("users", schema="app")
