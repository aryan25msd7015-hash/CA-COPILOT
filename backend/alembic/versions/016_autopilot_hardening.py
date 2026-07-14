"""Harden autopilot module indexes.

Revision ID: 016
Revises: 015
Create Date: 2026-06-19
"""

from alembic import op


revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_autopilot_sync_org_client_started", "autopilot_sync_runs", ["org_id", "client_id", "started_at"])
    op.create_index("idx_autopilot_exceptions_org_status_updated", "autopilot_exceptions", ["org_id", "status", "updated_at"])
    op.create_index("idx_autopilot_exceptions_org_client_status", "autopilot_exceptions", ["org_id", "client_id", "status"])
    op.create_index("idx_autopilot_exceptions_org_source", "autopilot_exceptions", ["org_id", "source_type"])
    op.create_index("idx_autopilot_followups_org_client_created", "autopilot_followups", ["org_id", "client_id", "created_at"])


def downgrade():
    op.drop_index("idx_autopilot_followups_org_client_created", table_name="autopilot_followups")
    op.drop_index("idx_autopilot_exceptions_org_source", table_name="autopilot_exceptions")
    op.drop_index("idx_autopilot_exceptions_org_client_status", table_name="autopilot_exceptions")
    op.drop_index("idx_autopilot_exceptions_org_status_updated", table_name="autopilot_exceptions")
    op.drop_index("idx_autopilot_sync_org_client_started", table_name="autopilot_sync_runs")
