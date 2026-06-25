"""Anomaly review workflow metadata.

Revision ID: 029
Revises: 028
Create Date: 2026-06-23 05:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("anomaly_flags", sa.Column("review_status", sa.String(length=30), nullable=False, server_default="open"))
    op.add_column("anomaly_flags", sa.Column("review_note", sa.Text(), nullable=True))
    op.add_column("anomaly_flags", sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("anomaly_flags", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_anomaly_flags_reviewed_by_user",
        "anomaly_flags",
        "users",
        ["reviewed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_anomaly_flags_reviewed_by_user", "anomaly_flags", ["reviewed_by_user_id"])
    op.create_index("idx_anomaly_flags_org_review_status", "anomaly_flags", ["org_id", "review_status"])
    op.execute("UPDATE anomaly_flags SET review_status = CASE WHEN reviewed THEN 'confirmed' ELSE 'open' END")


def downgrade() -> None:
    op.drop_index("idx_anomaly_flags_org_review_status", table_name="anomaly_flags")
    op.drop_index("idx_anomaly_flags_reviewed_by_user", table_name="anomaly_flags")
    op.drop_constraint("fk_anomaly_flags_reviewed_by_user", "anomaly_flags", type_="foreignkey")
    op.drop_column("anomaly_flags", "reviewed_at")
    op.drop_column("anomaly_flags", "reviewed_by_user_id")
    op.drop_column("anomaly_flags", "review_note")
    op.drop_column("anomaly_flags", "review_status")
