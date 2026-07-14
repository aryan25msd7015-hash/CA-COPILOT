"""practice operations modules

Revision ID: 006
Revises: 005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB

TENANT_TABLES = [
    "practice_tasks",
    "daybook_entries",
    "billing_plans",
    "practice_invoices",
    "payment_receipts",
    "client_portal_contacts",
    "portal_requests",
    "attendance_entries",
    "credential_vault_items",
    "import_jobs",
    "saved_views",
]


def base_columns():
    return [
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    ]


def client_column(nullable=True):
    return sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=nullable)


def user_column(name, nullable=True, ondelete="SET NULL"):
    return sa.Column(name, UUID, sa.ForeignKey("users.id", ondelete=ondelete), nullable=nullable)


def created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False)


def upgrade():
    op.create_table(
        "practice_tasks", *base_columns(), client_column(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("service_type", sa.String(40), nullable=False, server_default="compliance"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("stage", sa.String(30), nullable=False, server_default="maker"),
        sa.Column("due_date", sa.Date()),
        user_column("assigned_to"), user_column("reviewer_id"),
        sa.Column("checklist", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("recurring_rule", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("notes", sa.Text()), user_column("created_by"),
        sa.Column("completed_at", sa.DateTime(timezone=True)), created_at(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index("idx_practice_tasks_org", "practice_tasks", ["org_id"])
    op.create_index("idx_practice_tasks_client", "practice_tasks", ["client_id"])
    op.create_index("idx_practice_tasks_status", "practice_tasks", ["status"])
    op.create_index("idx_practice_tasks_due_date", "practice_tasks", ["due_date"])

    op.create_table(
        "daybook_entries", *base_columns(), client_column(),
        sa.Column("task_id", UUID, sa.ForeignKey("practice_tasks.id", ondelete="SET NULL")),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("activity_type", sa.String(40), nullable=False, server_default="follow_up"),
        sa.Column("summary", sa.Text(), nullable=False),
        user_column("assigned_to"),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        user_column("created_by"), created_at(),
    )
    op.create_index("idx_daybook_entries_org", "daybook_entries", ["org_id"])
    op.create_index("idx_daybook_entries_date", "daybook_entries", ["entry_date"])

    op.create_table(
        "billing_plans", *base_columns(), client_column(nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("service_scope", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("frequency", sa.String(20), nullable=False, server_default="monthly"),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="18"),
        sa.Column("next_invoice_date", sa.Date()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        created_at(),
    )
    op.create_index("idx_billing_plans_org", "billing_plans", ["org_id"])
    op.create_index("idx_billing_plans_client", "billing_plans", ["client_id"])

    op.create_table(
        "practice_invoices", *base_columns(), client_column(nullable=False),
        sa.Column("plan_id", UUID, sa.ForeignKey("billing_plans.id", ondelete="SET NULL")),
        sa.Column("invoice_no", sa.String(40), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("line_items", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("subtotal", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("tax", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("amount_paid", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("payment_link", sa.Text()), user_column("created_by"), created_at(),
        sa.UniqueConstraint("org_id", "invoice_no", name="uq_practice_invoice_no"),
    )
    op.create_index("idx_practice_invoices_org", "practice_invoices", ["org_id"])
    op.create_index("idx_practice_invoices_client", "practice_invoices", ["client_id"])
    op.create_index("idx_practice_invoices_status", "practice_invoices", ["status"])
    op.create_index("idx_practice_invoices_due_date", "practice_invoices", ["due_date"])

    op.create_table(
        "payment_receipts", *base_columns(),
        sa.Column("invoice_id", UUID, sa.ForeignKey("practice_invoices.id", ondelete="CASCADE"), nullable=False),
        client_column(nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("mode", sa.String(30), nullable=False, server_default="bank_transfer"),
        sa.Column("reference", sa.Text()), sa.Column("notes", sa.Text()), user_column("created_by"), created_at(),
    )
    op.create_index("idx_payment_receipts_org", "payment_receipts", ["org_id"])
    op.create_index("idx_payment_receipts_invoice", "payment_receipts", ["invoice_id"])

    op.create_table(
        "client_portal_contacts", *base_columns(), client_column(nullable=False),
        sa.Column("name", sa.Text(), nullable=False), sa.Column("email", sa.Text(), nullable=False),
        sa.Column("phone", sa.String(20)), sa.Column("role", sa.String(40), nullable=False, server_default="client_user"),
        sa.Column("access_status", sa.String(20), nullable=False, server_default="invited"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)), created_at(),
        sa.UniqueConstraint("client_id", "email", name="uq_portal_contact_email"),
    )
    op.create_index("idx_client_portal_contacts_org", "client_portal_contacts", ["org_id"])
    op.create_index("idx_client_portal_contacts_client", "client_portal_contacts", ["client_id"])

    op.create_table(
        "portal_requests", *base_columns(), client_column(nullable=False),
        sa.Column("contact_id", UUID, sa.ForeignKey("client_portal_contacts.id", ondelete="SET NULL")),
        sa.Column("request_type", sa.String(30), nullable=False, server_default="document"),
        sa.Column("title", sa.Text(), nullable=False), sa.Column("description", sa.Text()),
        sa.Column("due_date", sa.Date()), sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("attachments", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("response_summary", sa.Text()), user_column("created_by"), created_at(),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_portal_requests_org", "portal_requests", ["org_id"])
    op.create_index("idx_portal_requests_client", "portal_requests", ["client_id"])
    op.create_index("idx_portal_requests_status", "portal_requests", ["status"])
    op.create_index("idx_portal_requests_due_date", "portal_requests", ["due_date"])

    op.create_table(
        "attendance_entries", *base_columns(),
        user_column("user_id", nullable=False, ondelete="CASCADE"),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="present"),
        sa.Column("hours_available", sa.Numeric(5, 2), nullable=False, server_default="8"),
        sa.Column("hours_booked", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text()), created_at(),
        sa.UniqueConstraint("org_id", "user_id", "work_date", name="uq_attendance_user_date"),
    )
    op.create_index("idx_attendance_entries_org", "attendance_entries", ["org_id"])
    op.create_index("idx_attendance_entries_user", "attendance_entries", ["user_id"])
    op.create_index("idx_attendance_entries_date", "attendance_entries", ["work_date"])

    op.create_table(
        "credential_vault_items", *base_columns(), client_column(),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("credential_type", sa.String(30), nullable=False, server_default="portal"),
        sa.Column("username", sa.Text()), sa.Column("masked_secret", sa.Text()),
        sa.Column("storage_reference", sa.Text()), user_column("owner_user_id"),
        sa.Column("expires_on", sa.Date()),
        sa.Column("rotation_status", sa.String(20), nullable=False, server_default="current"),
        sa.Column("last_used_at", sa.DateTime(timezone=True)), sa.Column("notes", sa.Text()),
        user_column("created_by"), created_at(),
    )
    op.create_index("idx_credential_vault_items_org", "credential_vault_items", ["org_id"])
    op.create_index("idx_credential_vault_items_expires", "credential_vault_items", ["expires_on"])

    op.create_table(
        "import_jobs", *base_columns(), client_column(),
        sa.Column("import_type", sa.String(40), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("mapping", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("sample_rows", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("validation_errors", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("records_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_valid", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_imported", sa.Integer(), nullable=False, server_default="0"),
        user_column("created_by"), created_at(), sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("idx_import_jobs_org", "import_jobs", ["org_id"])
    op.create_index("idx_import_jobs_status", "import_jobs", ["status"])

    op.create_table(
        "saved_views", *base_columns(), user_column("user_id", nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("view_type", sa.String(40), nullable=False, server_default="report"),
        sa.Column("filters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("columns", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_shared", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")), created_at(),
    )
    op.create_index("idx_saved_views_org", "saved_views", ["org_id"])
    op.create_index("idx_saved_views_user", "saved_views", ["user_id"])

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
