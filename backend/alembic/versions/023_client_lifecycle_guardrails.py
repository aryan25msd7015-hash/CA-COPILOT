"""Client lifecycle guardrails.

Revision ID: 023
Revises: 022
Create Date: 2026-06-23 00:50:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("pan", sa.String(length=10), nullable=True))
    op.add_column("clients", sa.Column("tan", sa.String(length=10), nullable=True))
    op.add_column("clients", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
    op.add_column("clients", sa.Column("client_partition", sa.Text(), nullable=True))
    op.add_column("clients", sa.Column("lifecycle_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"))
    op.add_column("clients", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(sa.text("UPDATE clients SET client_partition = 'org_' || org_id::text || '\\:client_' || id::text WHERE client_partition IS NULL"))
    op.create_index("idx_clients_org_pan_unique", "clients", ["org_id", "pan"], unique=True, postgresql_where=sa.text("pan IS NOT NULL"))
    op.create_index("idx_clients_org_status", "clients", ["org_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_clients_org_status", table_name="clients")
    op.drop_index("idx_clients_org_pan_unique", table_name="clients")
    op.drop_column("clients", "deleted_at")
    op.drop_column("clients", "lifecycle_metadata")
    op.drop_column("clients", "client_partition")
    op.drop_column("clients", "status")
    op.drop_column("clients", "tan")
    op.drop_column("clients", "pan")
