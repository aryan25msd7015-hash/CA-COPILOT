"""Add organization onboarding audit and agent readiness.

Revision ID: 019
Revises: 018
Create Date: 2026-06-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("pan", sa.String(length=10), nullable=True))
    op.add_column("organizations", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column("organizations", sa.Column("firm_type", sa.String(length=30), nullable=False, server_default="ca_firm"))
    op.create_index(
        "idx_organizations_pan_unique",
        "organizations",
        ["pan"],
        unique=True,
        postgresql_where=sa.text("pan IS NOT NULL"),
    )

    op.create_table(
        "system_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_system_audit_logs_org_id", "system_audit_logs", ["org_id"])
    op.create_index("idx_system_audit_logs_actor_id", "system_audit_logs", ["actor_id"])
    op.create_index("idx_system_audit_org_created", "system_audit_logs", ["org_id", "created_at"])
    op.create_index("idx_system_audit_actor_created", "system_audit_logs", ["actor_id", "created_at"])

    op.create_table(
        "organization_agent_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ready"),
        sa.Column("vector_namespace", sa.Text(), nullable=False),
        sa.Column("enabled_agents", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("readiness_checks", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_event", sa.String(length=80), nullable=False, server_default="organization.initialized"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_organization_agent_states_org_id", "organization_agent_states", ["org_id"])
    op.create_index("idx_agent_state_org_status", "organization_agent_states", ["org_id", "status"])

    for table in ("system_audit_logs", "organization_agent_states"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )


def downgrade():
    for table in ("organization_agent_states", "system_audit_logs"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.drop_index("idx_agent_state_org_status", table_name="organization_agent_states")
    op.drop_index("idx_organization_agent_states_org_id", table_name="organization_agent_states")
    op.drop_table("organization_agent_states")
    op.drop_index("idx_system_audit_actor_created", table_name="system_audit_logs")
    op.drop_index("idx_system_audit_org_created", table_name="system_audit_logs")
    op.drop_index("idx_system_audit_logs_actor_id", table_name="system_audit_logs")
    op.drop_index("idx_system_audit_logs_org_id", table_name="system_audit_logs")
    op.drop_table("system_audit_logs")
    op.drop_index("idx_organizations_pan_unique", table_name="organizations")
    op.drop_column("organizations", "firm_type")
    op.drop_column("organizations", "status")
    op.drop_column("organizations", "pan")
