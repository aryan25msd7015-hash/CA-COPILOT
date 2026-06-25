"""Saved query workflow metadata.

Revision ID: 031
Revises: 030
Create Date: 2026-06-23 06:05:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("saved_queries", sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("saved_queries", sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("saved_queries", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_index("idx_saved_queries_org_user_updated", "saved_queries", ["org_id", "user_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_saved_queries_org_user_updated", table_name="saved_queries")
    op.drop_column("saved_queries", "updated_at")
    op.drop_column("saved_queries", "last_run_at")
    op.drop_column("saved_queries", "run_count")
