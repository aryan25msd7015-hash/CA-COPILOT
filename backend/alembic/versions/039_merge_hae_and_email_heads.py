"""Merge HAE migration chain with Razorpay/email branch.

Revision ID: 039
Revises: 038, 20260114_email
Create Date: 2026-07-27 17:12:00.000000
"""
from alembic import op  # noqa: F401


revision = "039"
down_revision = ("038", "20260114_email")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
