"""Reconciliation run lifecycle metadata.

Revision ID: 027
Revises: 026
Create Date: 2026-06-23 03:24:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reconciliation_results", sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"))
    op.add_column("reconciliation_results", sa.Column("task_id", sa.String(length=50), nullable=True))
    op.add_column("reconciliation_results", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "reconciliation_results",
        sa.Column("input_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column("reconciliation_results", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE reconciliation_results SET completed_at = run_at WHERE completed_at IS NULL")
    op.create_check_constraint(
        "ck_reconciliation_results_status",
        "reconciliation_results",
        "status IN ('queued','running','completed','failed')",
    )
    op.create_index(
        "idx_reconciliation_results_org_client_status",
        "reconciliation_results",
        ["org_id", "client_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_reconciliation_results_org_client_status", table_name="reconciliation_results")
    op.drop_constraint("ck_reconciliation_results_status", "reconciliation_results", type_="check")
    op.drop_column("reconciliation_results", "completed_at")
    op.drop_column("reconciliation_results", "input_summary")
    op.drop_column("reconciliation_results", "error_message")
    op.drop_column("reconciliation_results", "task_id")
    op.drop_column("reconciliation_results", "status")
