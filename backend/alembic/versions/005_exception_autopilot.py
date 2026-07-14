"""exception autopilot

Revision ID: 005
Revises: 004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB

TENANT_TABLES = [
    "autopilot_sync_runs",
    "autopilot_exceptions",
    "autopilot_review_actions",
    "autopilot_followups",
]


def base_columns():
    return [
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    ]


def client_column(nullable=True):
    return sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=nullable)


def created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False)


def upgrade():
    op.create_table(
        "autopilot_sync_runs", *base_columns(), client_column(),
        sa.Column("source", sa.String(30), nullable=False, server_default="tally_connector"),
        sa.Column("source_name", sa.Text()),
        sa.Column("period", sa.String(20)),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("records_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("idx_autopilot_sync_runs_org", "autopilot_sync_runs", ["org_id"])
    op.create_index("idx_autopilot_sync_runs_client", "autopilot_sync_runs", ["client_id"])

    op.create_table(
        "autopilot_exceptions", *base_columns(), client_column(),
        sa.Column("fingerprint", sa.String(180), nullable=False),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("source_id", UUID),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("impact_amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("due_date", sa.Date()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("owner_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("evidence", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("recommended_actions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("org_id", "fingerprint", name="uq_autopilot_exception_fingerprint"),
    )
    op.create_index("idx_autopilot_exceptions_org", "autopilot_exceptions", ["org_id"])
    op.create_index("idx_autopilot_exceptions_client", "autopilot_exceptions", ["client_id"])
    op.create_index("idx_autopilot_exceptions_status", "autopilot_exceptions", ["status"])

    op.create_table(
        "autopilot_review_actions", *base_columns(),
        sa.Column("exception_id", UUID, sa.ForeignKey("autopilot_exceptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        created_at(),
    )
    op.create_index("idx_autopilot_review_actions_org", "autopilot_review_actions", ["org_id"])
    op.create_index("idx_autopilot_review_actions_exception", "autopilot_review_actions", ["exception_id"])

    op.create_table(
        "autopilot_followups", *base_columns(), client_column(nullable=False),
        sa.Column("exception_id", UUID, sa.ForeignKey("autopilot_exceptions.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(20), nullable=False, server_default="whatsapp"),
        sa.Column("template", sa.String(60), nullable=False, server_default="autopilot_document_request"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("response_summary", sa.Text()),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        created_at(),
    )
    op.create_index("idx_autopilot_followups_org", "autopilot_followups", ["org_id"])
    op.create_index("idx_autopilot_followups_client", "autopilot_followups", ["client_id"])
    op.create_index("idx_autopilot_followups_exception", "autopilot_followups", ["exception_id"])

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )


def downgrade():
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
