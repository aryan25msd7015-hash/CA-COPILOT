"""Harden reconciliation indexes.

Revision ID: 011
Revises: 010
Create Date: 2026-06-19
"""

from alembic import op


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_transactions_org_client_created", "transactions", ["org_id", "client_id", "created_at"])
    op.create_index("idx_transactions_org_client_date", "transactions", ["org_id", "client_id", "date"])
    op.create_index("idx_transactions_org_match_status", "transactions", ["org_id", "match_status"])
    op.create_index("idx_reconciliation_results_org_client_run", "reconciliation_results", ["org_id", "client_id", "run_at"])


def downgrade():
    op.drop_index("idx_reconciliation_results_org_client_run", table_name="reconciliation_results")
    op.drop_index("idx_transactions_org_match_status", table_name="transactions")
    op.drop_index("idx_transactions_org_client_date", table_name="transactions")
    op.drop_index("idx_transactions_org_client_created", table_name="transactions")
