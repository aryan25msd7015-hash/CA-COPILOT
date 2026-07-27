"""HAE-5 precision audit fields on transactions.

Revision ID: 038
Revises: 037
Create Date: 2026-07-27 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("audit_confidence", sa.Numeric(5, 4), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("audit_assertions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("audit_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index(
        "idx_transactions_org_audit_confidence",
        "transactions",
        ["org_id", "audit_confidence"],
    )


def downgrade() -> None:
    op.drop_index("idx_transactions_org_audit_confidence", table_name="transactions")
    op.drop_column("transactions", "audit_meta")
    op.drop_column("transactions", "audit_assertions")
    op.drop_column("transactions", "audit_confidence")
