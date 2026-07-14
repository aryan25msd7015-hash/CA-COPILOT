"""Session lifecycle hardening.

Revision ID: 020
Revises: 019
Create Date: 2026-06-22 23:58:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("fingerprint_hash", sa.String(length=64), nullable=False, server_default=""))
    op.add_column("refresh_tokens", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("refresh_tokens", sa.Column("user_agent", sa.Text(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("hard_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("replay_detected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("refresh_tokens", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE refresh_tokens SET hard_expires_at = expires_at WHERE hard_expires_at IS NULL")
    op.create_index("idx_refresh_tokens_user_active", "refresh_tokens", ["user_id", "revoked", "created_at"])
    op.create_index("idx_refresh_tokens_fingerprint", "refresh_tokens", ["fingerprint_hash"])


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_fingerprint", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_user_active", table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "last_used_at")
    op.drop_column("refresh_tokens", "replay_detected_at")
    op.drop_column("refresh_tokens", "hard_expires_at")
    op.drop_column("refresh_tokens", "user_agent")
    op.drop_column("refresh_tokens", "ip_address")
    op.drop_column("refresh_tokens", "fingerprint_hash")
