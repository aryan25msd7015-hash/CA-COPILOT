"""Harden audit anomaly invoice modules.

Revision ID: 014
Revises: 013
Create Date: 2026-06-19
"""

from alembic import op


revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_anomaly_flags_org_review_risk", "anomaly_flags", ["org_id", "reviewed", "risk_score"])
    op.create_index("idx_anomaly_flags_org_client_risk", "anomaly_flags", ["org_id", "client_id", "risk_score"])
    op.create_index("idx_anomaly_flags_org_type", "anomaly_flags", ["org_id", "flag_type"])


def downgrade():
    op.drop_index("idx_anomaly_flags_org_type", table_name="anomaly_flags")
    op.drop_index("idx_anomaly_flags_org_client_risk", table_name="anomaly_flags")
    op.drop_index("idx_anomaly_flags_org_review_risk", table_name="anomaly_flags")
