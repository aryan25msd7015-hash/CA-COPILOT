"""row level security policies

Revision ID: 002
Revises: 001
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

TENANT_TABLES = [
    "clients", "documents", "transactions", "compliance_deadlines",
    "whatsapp_reminders", "reconciliation_results", "client_health_history",
    "anomaly_flags", "saved_queries",
]


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )
    op.execute("ALTER TABLE reconciliation_config ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY reconciliation_config_tenant_policy ON reconciliation_config "
        "USING (EXISTS (SELECT 1 FROM clients c WHERE c.id = client_id AND "
        "c.org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid))"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS reconciliation_config_tenant_policy ON reconciliation_config")
    op.execute("ALTER TABLE reconciliation_config DISABLE ROW LEVEL SECURITY")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
