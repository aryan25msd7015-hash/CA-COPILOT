"""Organization profile isolation settings.

Revision ID: 021
Revises: 020
Create Date: 2026-06-23 00:12:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("frn", sa.String(length=20), nullable=True))
    op.add_column("organizations", sa.Column("registered_state", sa.String(length=40), nullable=True))
    op.add_column("organizations", sa.Column("jurisdictions", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"))
    op.add_column("organizations", sa.Column("compliance_profile", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"))
    op.add_column("organizations", sa.Column("automation_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"))
    op.add_column("organizations", sa.Column("data_residency_region", sa.String(length=40), nullable=False, server_default="IN"))
    op.add_column("organizations", sa.Column("key_vault_ref", sa.Text(), nullable=True))
    op.add_column("organizations", sa.Column("security_policy", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"))
    op.add_column("organizations", sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("idx_organizations_residency", "organizations", ["data_residency_region"])


def downgrade() -> None:
    op.drop_index("idx_organizations_residency", table_name="organizations")
    op.drop_column("organizations", "config_version")
    op.drop_column("organizations", "security_policy")
    op.drop_column("organizations", "key_vault_ref")
    op.drop_column("organizations", "data_residency_region")
    op.drop_column("organizations", "automation_policy")
    op.drop_column("organizations", "compliance_profile")
    op.drop_column("organizations", "jurisdictions")
    op.drop_column("organizations", "registered_state")
    op.drop_column("organizations", "frn")
