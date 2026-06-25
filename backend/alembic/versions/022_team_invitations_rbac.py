"""Team invitations and RBAC lifecycle.

Revision ID: 022
Revises: 021
Create Date: 2026-06-23 00:32:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("status", sa.String(length=20), nullable=False, server_default="active"))
    op.create_table(
        "team_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_team_invites_org_status", "team_invitations", ["org_id", "status"])
    op.create_index("idx_team_invites_token_hash", "team_invitations", ["token_hash"], unique=True)
    op.create_index(op.f("ix_team_invitations_org_id"), "team_invitations", ["org_id"])
    op.create_index(op.f("ix_team_invitations_invited_by_user_id"), "team_invitations", ["invited_by_user_id"])
    op.execute("ALTER TABLE team_invitations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY team_invitations_tenant_isolation ON team_invitations
        USING (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
        WITH CHECK (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS team_invitations_tenant_isolation ON team_invitations")
    op.drop_index(op.f("ix_team_invitations_invited_by_user_id"), table_name="team_invitations")
    op.drop_index(op.f("ix_team_invitations_org_id"), table_name="team_invitations")
    op.drop_index("idx_team_invites_token_hash", table_name="team_invitations")
    op.drop_index("idx_team_invites_org_status", table_name="team_invitations")
    op.drop_table("team_invitations")
    op.drop_column("users", "status")
