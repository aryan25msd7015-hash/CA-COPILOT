"""Harden advanced extension indexes.

Revision ID: 018
Revises: 017
Create Date: 2026-06-19
"""

from alembic import op


revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_msme_vendors_org_client_created", "msme_vendors", ["org_id", "client_id", "created_at"])
    op.create_index("idx_msme_violations_org_client_fy", "msme_payment_violations", ["org_id", "client_id", "fy"])
    op.create_index("idx_bank_facilities_org_client", "bank_facilities", ["org_id", "client_id"])
    op.create_index("idx_certificate_records_org_client_created", "certificate_records", ["org_id", "client_id", "created_at"])
    op.create_index("idx_secretarial_documents_org_client_created", "secretarial_documents", ["org_id", "client_id", "created_at"])
    op.create_index("idx_lease_records_org_client_created", "lease_records", ["org_id", "client_id", "created_at"])
    op.create_index("idx_rfp_bids_org_created", "rfp_bids", ["org_id", "created_at"])


def downgrade():
    op.drop_index("idx_rfp_bids_org_created", table_name="rfp_bids")
    op.drop_index("idx_lease_records_org_client_created", table_name="lease_records")
    op.drop_index("idx_secretarial_documents_org_client_created", table_name="secretarial_documents")
    op.drop_index("idx_certificate_records_org_client_created", table_name="certificate_records")
    op.drop_index("idx_bank_facilities_org_client", table_name="bank_facilities")
    op.drop_index("idx_msme_violations_org_client_fy", table_name="msme_payment_violations")
    op.drop_index("idx_msme_vendors_org_client_created", table_name="msme_vendors")
