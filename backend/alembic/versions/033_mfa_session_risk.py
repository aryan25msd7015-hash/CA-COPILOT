"""MFA and session risk hardening.

Revision ID: 033
Revises: 032
Create Date: 2026-06-24 10:30:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_secret", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_recovery_hashes", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("mfa_confirmed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("idx_users_org_mfa", "users", ["org_id", "mfa_enabled"])

    op.add_column("refresh_tokens", sa.Column("risk_score", sa.String(length=20), nullable=False, server_default="low"))
    op.add_column("refresh_tokens", sa.Column("risk_reasons", sa.Text(), nullable=True))
    op.create_index("idx_refresh_tokens_risk", "refresh_tokens", ["org_id", "user_id", "risk_score"])


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_risk", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "risk_reasons")
    op.drop_column("refresh_tokens", "risk_score")

    op.drop_index("idx_users_org_mfa", table_name="users")
    op.drop_column("users", "mfa_confirmed_at")
    op.drop_column("users", "mfa_recovery_hashes")
    op.drop_column("users", "mfa_secret")
    op.drop_column("users", "mfa_enabled")
