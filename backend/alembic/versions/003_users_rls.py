"""Add the missing tenant policy for users.

Revision ID: 003
Revises: 002
"""
from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY users_tenant_policy ON users "
        "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
        "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_tenant_policy ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")
