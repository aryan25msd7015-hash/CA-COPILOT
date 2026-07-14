"""Benchmark consent metadata.

Revision ID: 032
Revises: 031
Create Date: 2026-06-23 06:12:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("benchmark_consent_source", sa.String(length=30), nullable=True))
    op.add_column("clients", sa.Column("benchmark_consent_note", sa.Text(), nullable=True))
    op.add_column("clients", sa.Column("benchmark_consent_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_clients_benchmark_consent_user",
        "clients",
        "users",
        ["benchmark_consent_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_clients_benchmark_consent_user", "clients", ["benchmark_consent_by_user_id"])


def downgrade() -> None:
    op.drop_index("idx_clients_benchmark_consent_user", table_name="clients")
    op.drop_constraint("fk_clients_benchmark_consent_user", "clients", type_="foreignkey")
    op.drop_column("clients", "benchmark_consent_by_user_id")
    op.drop_column("clients", "benchmark_consent_note")
    op.drop_column("clients", "benchmark_consent_source")
