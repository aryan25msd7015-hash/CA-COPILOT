"""Reconciliation manual cockpit actions.

Revision ID: 035
Revises: 034
Create Date: 2026-06-24 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reconciliation_match_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purchase_transaction_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gstr2b_transaction_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_type", sa.String(length=30), nullable=False),
        sa.Column("previous_status", sa.String(length=15), nullable=True),
        sa.Column("previous_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("new_status", sa.String(length=15), nullable=False),
        sa.Column("new_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action_type IN ('manual_match','unmatch','rollback')", name="ck_recon_actions_type"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["result_id"], ["reconciliation_results.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_transaction_id"], ["transactions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["gstr2b_transaction_id"], ["transactions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("idx_recon_actions_org_client_created", "reconciliation_match_actions", ["org_id", "client_id", "created_at"])
    op.create_index("idx_recon_actions_purchase", "reconciliation_match_actions", ["org_id", "purchase_transaction_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_recon_actions_purchase", table_name="reconciliation_match_actions")
    op.drop_index("idx_recon_actions_org_client_created", table_name="reconciliation_match_actions")
    op.drop_table("reconciliation_match_actions")
