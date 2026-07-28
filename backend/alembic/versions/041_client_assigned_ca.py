"""Add assigned CA ownership on clients.

Revision ID: 041
Revises: 040
Create Date: 2026-07-28 10:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("assigned_ca_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("idx_clients_org_assigned_ca", "clients", ["org_id", "assigned_ca_user_id"])


def downgrade() -> None:
    op.drop_index("idx_clients_org_assigned_ca", table_name="clients")
    op.drop_column("clients", "assigned_ca_user_id")
