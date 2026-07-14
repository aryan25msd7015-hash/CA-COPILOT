"""Harden query and benchmarking modules.

Revision ID: 015
Revises: 014
Create Date: 2026-06-19
"""

from alembic import op


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_saved_queries_user_name", "saved_queries", ["org_id", "user_id", "name"])
    op.create_index("idx_saved_queries_org_user_created", "saved_queries", ["org_id", "user_id", "created_at"])


def downgrade():
    op.drop_index("idx_saved_queries_org_user_created", table_name="saved_queries")
    op.drop_constraint("uq_saved_queries_user_name", "saved_queries", type_="unique")
