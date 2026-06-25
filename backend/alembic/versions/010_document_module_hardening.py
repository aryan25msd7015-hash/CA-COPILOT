"""Harden document module indexes.

Revision ID: 010
Revises: 009
Create Date: 2026-06-19
"""

from alembic import op


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_documents_org_created", "documents", ["org_id", "created_at"])
    op.create_index("idx_documents_org_client_created", "documents", ["org_id", "client_id", "created_at"])
    op.create_index("idx_documents_org_type_status", "documents", ["org_id", "doc_type", "status"])


def downgrade():
    op.drop_index("idx_documents_org_type_status", table_name="documents")
    op.drop_index("idx_documents_org_client_created", table_name="documents")
    op.drop_index("idx_documents_org_created", table_name="documents")
