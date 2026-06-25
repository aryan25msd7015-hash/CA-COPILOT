"""Harden deadline module indexes.

Revision ID: 012
Revises: 011
Create Date: 2026-06-19
"""

from alembic import op


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_deadlines_org_deadline", "compliance_deadlines", ["org_id", "deadline"])
    op.create_index("idx_deadlines_org_client_deadline", "compliance_deadlines", ["org_id", "client_id", "deadline"])
    op.create_index("idx_deadlines_org_client_filing_period", "compliance_deadlines", ["org_id", "client_id", "filing_type", "period"])
    op.create_index("idx_deadlines_org_status_deadline", "compliance_deadlines", ["org_id", "status", "deadline"])


def downgrade():
    op.drop_index("idx_deadlines_org_status_deadline", table_name="compliance_deadlines")
    op.drop_index("idx_deadlines_org_client_filing_period", table_name="compliance_deadlines")
    op.drop_index("idx_deadlines_org_client_deadline", table_name="compliance_deadlines")
    op.drop_index("idx_deadlines_org_deadline", table_name="compliance_deadlines")
