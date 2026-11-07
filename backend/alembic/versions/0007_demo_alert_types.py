"""Explicit demonstration-rule alert types, distinct from model thresholds."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None
BASE = ("model_threshold", "graph_structural", "manual")
DEMO = ("demo_rule_unusual", "demo_rule_incoming", "demo_rule_redistribution", "demo_rule_linked")


def upgrade():
    op.drop_constraint(
        op.f("ck_alerts_ck_alerts_alert_type"), "alerts", schema="app", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_alerts_ck_alerts_alert_type"),
        "alerts",
        f"alert_type IN {BASE + DEMO!r}",
        schema="app",
    )


def downgrade():
    # PostgreSQL refuses downgrade while demo rules exist. Reset owned batches first.
    op.drop_constraint(
        op.f("ck_alerts_ck_alerts_alert_type"), "alerts", schema="app", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_alerts_ck_alerts_alert_type"), "alerts", f"alert_type IN {BASE!r}", schema="app"
    )
