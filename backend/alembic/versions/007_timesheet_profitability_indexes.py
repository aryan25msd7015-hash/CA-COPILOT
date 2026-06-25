"""Add indexes for timesheet profitability aggregates.

Revision ID: 007
Revises: 006_practice_ops
Create Date: 2026-06-18
"""

from alembic import op


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "idx_user_activity_log_org_client_created",
        "user_activity_log",
        ["org_id", "client_id", "created_at"],
    )
    op.create_index(
        "idx_timesheet_entries_org_client_date",
        "timesheet_entries",
        ["org_id", "client_id", "date"],
    )


def downgrade():
    op.drop_index("idx_timesheet_entries_org_client_date", table_name="timesheet_entries")
    op.drop_index("idx_user_activity_log_org_client_created", table_name="user_activity_log")
