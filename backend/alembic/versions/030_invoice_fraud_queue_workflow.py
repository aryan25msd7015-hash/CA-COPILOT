"""Invoice fraud queue workflow metadata.

Revision ID: 030
Revises: 029
Create Date: 2026-06-23 05:55:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("fraud_review_status", sa.String(length=30), nullable=False, server_default="open"))
    op.add_column("transactions", sa.Column("fraud_review_note", sa.Text(), nullable=True))
    op.add_column("transactions", sa.Column("fraud_reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("transactions", sa.Column("fraud_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transactions", sa.Column("fraud_scanned_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_transactions_fraud_reviewed_by_user",
        "transactions",
        "users",
        ["fraud_reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_transactions_fraud_reviewed_by_user", "transactions", ["fraud_reviewed_by_user_id"])
    op.create_index("idx_transactions_org_fraud_status", "transactions", ["org_id", "fraud_review_status"])


def downgrade() -> None:
    op.drop_index("idx_transactions_org_fraud_status", table_name="transactions")
    op.drop_index("idx_transactions_fraud_reviewed_by_user", table_name="transactions")
    op.drop_constraint("fk_transactions_fraud_reviewed_by_user", "transactions", type_="foreignkey")
    op.drop_column("transactions", "fraud_scanned_at")
    op.drop_column("transactions", "fraud_reviewed_at")
    op.drop_column("transactions", "fraud_reviewed_by_user_id")
    op.drop_column("transactions", "fraud_review_note")
    op.drop_column("transactions", "fraud_review_status")
