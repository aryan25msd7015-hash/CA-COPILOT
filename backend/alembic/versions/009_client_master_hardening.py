"""Harden client master data.

Revision ID: 009
Revises: 008
Create Date: 2026-06-19
"""

import sqlalchemy as sa
from alembic import op


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_check_constraint(
        "ck_clients_health_score",
        "clients",
        "health_score >= 0 AND health_score <= 100",
    )
    op.create_check_constraint(
        "ck_clients_entity_type",
        "clients",
        "entity_type IN ('pvt_ltd','llp','partnership','proprietorship','trust')",
    )
    op.create_index("idx_clients_org_health_name", "clients", ["org_id", "health_score", "name"])
    op.create_index(
        "idx_clients_org_gstin_unique",
        "clients",
        ["org_id", "gstin"],
        unique=True,
        postgresql_where=sa.text("gstin IS NOT NULL"),
    )


def downgrade():
    op.drop_index("idx_clients_org_gstin_unique", table_name="clients")
    op.drop_index("idx_clients_org_health_name", table_name="clients")
    op.drop_constraint("ck_clients_entity_type", "clients", type_="check")
    op.drop_constraint("ck_clients_health_score", "clients", type_="check")
