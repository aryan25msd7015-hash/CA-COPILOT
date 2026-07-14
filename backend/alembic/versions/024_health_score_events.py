"""Health score event timeline.

Revision ID: 024
Revises: 023
Create Date: 2026-06-23 01:05:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "client_health_score_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("previous_score", sa.Integer(), nullable=True),
        sa.Column("current_score", sa.Integer(), nullable=False),
        sa.Column("delta", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reason_manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_health_events_org_client_created", "client_health_score_events", ["org_id", "client_id", "created_at"])
    op.create_index("idx_health_events_org_severity", "client_health_score_events", ["org_id", "severity"])
    op.create_index(op.f("ix_client_health_score_events_org_id"), "client_health_score_events", ["org_id"])
    op.create_index(op.f("ix_client_health_score_events_client_id"), "client_health_score_events", ["client_id"])
    op.execute("ALTER TABLE client_health_score_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY health_events_tenant_isolation ON client_health_score_events
        USING (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS health_events_tenant_isolation ON client_health_score_events")
    op.drop_index(op.f("ix_client_health_score_events_client_id"), table_name="client_health_score_events")
    op.drop_index(op.f("ix_client_health_score_events_org_id"), table_name="client_health_score_events")
    op.drop_index("idx_health_events_org_severity", table_name="client_health_score_events")
    op.drop_index("idx_health_events_org_client_created", table_name="client_health_score_events")
    op.drop_table("client_health_score_events")
