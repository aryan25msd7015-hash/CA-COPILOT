"""System event orchestration ledger.

Revision ID: 034
Revises: 033
Create Date: 2026-06-24 11:10:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "system_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("aggregate_type", sa.String(length=60), nullable=False),
        sa.Column("aggregate_id", sa.String(length=80), nullable=False),
        sa.Column("source_module", sa.String(length=60), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="recorded"),
        sa.Column("correlation_id", sa.String(length=80), nullable=False),
        sa.Column("causation_id", sa.String(length=80), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dispatch_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_system_events_org_created", "system_events", ["org_id", "created_at"])
    op.create_index("idx_system_events_org_status", "system_events", ["org_id", "status", "created_at"])
    op.create_index("idx_system_events_org_type", "system_events", ["org_id", "event_type", "created_at"])
    op.create_index("idx_system_events_aggregate", "system_events", ["org_id", "aggregate_type", "aggregate_id"])
    op.create_index("idx_system_events_correlation", "system_events", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("idx_system_events_correlation", table_name="system_events")
    op.drop_index("idx_system_events_aggregate", table_name="system_events")
    op.drop_index("idx_system_events_org_type", table_name="system_events")
    op.drop_index("idx_system_events_org_status", table_name="system_events")
    op.drop_index("idx_system_events_org_created", table_name="system_events")
    op.drop_table("system_events")
