"""new automation modules

Revision ID: 004
Revises: 003
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB

TENANT_TABLES = [
    "deadline_client_map", "msme_vendors", "msme_payment_violations",
    "bank_facilities", "inventory_items", "debtor_items",
    "drawing_power_statements", "certificate_records",
    "secretarial_documents", "lease_records", "firm_credentials", "rfp_bids",
    "user_activity_log", "timesheet_entries",
]


def base_columns():
    return [
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
    ]


def client_column(nullable=False):
    return sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=nullable)


def created_at():
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False)


def upgrade():
    op.add_column("clients", sa.Column("entity_type", sa.String(30), nullable=False, server_default="pvt_ltd"))
    op.add_column("clients", sa.Column("cin", sa.String(30)))
    op.add_column("clients", sa.Column("registered_office", sa.Text()))

    op.drop_constraint("ck_documents_doc_type", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_doc_type", "documents",
        "doc_type IN ('invoice','gstr2b','purchase_register','notice','trial_balance','bank_statement',"
        "'udyam_certificate','inventory_ledger','debtor_ledger','balance_sheet','pnl','itr','gstr9',"
        "'lease_agreement','rfp','board_transcript')",
    )

    op.create_table(
        "deadline_client_map", *base_columns(), client_column(),
        sa.Column("filing_type", sa.String(30), nullable=False),
        sa.Column("filing_name", sa.Text(), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("data_received", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("data_received_at", sa.DateTime(timezone=True)),
        sa.Column("data_source", sa.String(20)),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("filed_at", sa.DateTime(timezone=True)),
        sa.Column("late_count_last_12m", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("has_open_notice", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("risk_score", sa.Numeric(4, 1), nullable=False, server_default="0"),
        sa.Column("reminders_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_reminder_at", sa.DateTime(timezone=True)), created_at(),
        sa.UniqueConstraint("client_id", "filing_type", "period", name="uq_deadline_client_period"),
    )
    op.create_index("idx_deadline_client_map_org", "deadline_client_map", ["org_id"])
    op.create_index("idx_deadline_client_map_deadline", "deadline_client_map", ["deadline"])

    op.create_table(
        "msme_vendors", *base_columns(), client_column(),
        sa.Column("vendor_gstin", sa.String(15)), sa.Column("vendor_name", sa.Text(), nullable=False),
        sa.Column("udyam_reg_no", sa.String(30)), sa.Column("udyam_category", sa.String(10), nullable=False),
        sa.Column("udyam_cert_doc_id", UUID, sa.ForeignKey("documents.id", ondelete="SET NULL")),
        sa.Column("registered_at", sa.Date()), sa.Column("verified_at", sa.DateTime(timezone=True)),
        created_at(), sa.UniqueConstraint("client_id", "vendor_gstin", name="uq_msme_vendor_client_gstin"),
    )
    op.create_index("idx_msme_vendors_org", "msme_vendors", ["org_id"])

    op.create_table(
        "msme_payment_violations", *base_columns(), client_column(),
        sa.Column("vendor_id", UUID, sa.ForeignKey("msme_vendors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_id", UUID, sa.ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False), sa.Column("invoice_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False), sa.Column("payment_date", sa.Date()),
        sa.Column("days_overdue", sa.Integer(), nullable=False),
        sa.Column("disallowance_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("interest_amount", sa.Numeric(15, 2), nullable=False),
        sa.Column("fy", sa.String(10), nullable=False), sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        created_at(), sa.UniqueConstraint("vendor_id", "invoice_id", name="uq_msme_violation_invoice"),
    )
    op.create_index("idx_msme_violations_org", "msme_payment_violations", ["org_id"])

    op.create_table(
        "bank_facilities", *base_columns(), client_column(),
        sa.Column("bank_name", sa.Text(), nullable=False), sa.Column("facility_type", sa.String(10), nullable=False, server_default="CC"),
        sa.Column("sanctioned_limit", sa.Numeric(15, 2), nullable=False),
        sa.Column("margin_rules", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), created_at(),
    )
    op.create_index("idx_bank_facilities_org", "bank_facilities", ["org_id"])

    for table, columns in (
        ("inventory_items", [
            sa.Column("period", sa.String(20), nullable=False), sa.Column("sku", sa.String(80), nullable=False),
            sa.Column("description", sa.Text()), sa.Column("stock_value", sa.Numeric(15, 2), nullable=False),
            sa.Column("last_movement_date", sa.Date()),
        ]),
        ("debtor_items", [
            sa.Column("period", sa.String(20), nullable=False), sa.Column("debtor_name", sa.Text(), nullable=False),
            sa.Column("invoice_date", sa.Date(), nullable=False), sa.Column("outstanding", sa.Numeric(15, 2), nullable=False),
            sa.Column("payment_history_score", sa.Numeric(5, 2), nullable=False, server_default="100"),
        ]),
    ):
        op.create_table(table, *base_columns(), client_column(), *columns, created_at())
        op.create_index(f"idx_{table}_org", table, ["org_id"])

    op.create_table(
        "drawing_power_statements", *base_columns(), client_column(),
        sa.Column("facility_id", UUID, sa.ForeignKey("bank_facilities.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("gross_stock", sa.Numeric(15, 2), nullable=False), sa.Column("eligible_stock", sa.Numeric(15, 2), nullable=False),
        sa.Column("gross_debtors", sa.Numeric(15, 2), nullable=False), sa.Column("eligible_debtors", sa.Numeric(15, 2), nullable=False),
        sa.Column("creditors", sa.Numeric(15, 2), nullable=False), sa.Column("drawing_power", sa.Numeric(15, 2), nullable=False),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), created_at(),
        sa.UniqueConstraint("facility_id", "period", name="uq_dp_facility_period"),
    )
    op.create_index("idx_drawing_power_statements_org", "drawing_power_statements", ["org_id"])

    op.create_table(
        "certificate_records", *base_columns(), client_column(),
        sa.Column("cert_type", sa.String(40), nullable=False), sa.Column("title", sa.Text(), nullable=False),
        sa.Column("fields", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("validation", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")), created_at(),
    )
    op.create_index("idx_certificate_records_org", "certificate_records", ["org_id"])

    op.create_table(
        "secretarial_documents", *base_columns(), client_column(),
        sa.Column("doc_type", sa.String(30), nullable=False), sa.Column("transcript", sa.Text()),
        sa.Column("structured_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("generated_text", sa.Text(), nullable=False), sa.Column("generated_xml", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")), created_at(),
    )
    op.create_index("idx_secretarial_documents_org", "secretarial_documents", ["org_id"])

    op.create_table(
        "lease_records", *base_columns(), client_column(),
        sa.Column("name", sa.Text(), nullable=False), sa.Column("source_text", sa.Text()),
        sa.Column("extracted_data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("schedule", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("ibr_assumed", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")), created_at(),
    )
    op.create_index("idx_lease_records_org", "lease_records", ["org_id"])

    op.create_table(
        "firm_credentials", *base_columns(),
        sa.Column("firm_name", sa.Text(), nullable=False), sa.Column("icai_regn_no", sa.Text()),
        sa.Column("founding_year", sa.Integer()), sa.Column("hq_city", sa.Text()), sa.Column("hq_state", sa.Text()),
        sa.Column("partners", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("article_clerks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_staff", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gross_fee_receipts_fy1", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("gross_fee_receipts_fy2", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("gross_fee_receipts_fy3", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("industries_served", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("key_engagements", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("peer_review_status", sa.Text()), sa.Column("quality_review_date", sa.Date()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("org_id", name="uq_firm_credentials_org"),
    )

    op.create_table(
        "rfp_bids", *base_columns(), sa.Column("title", sa.Text(), nullable=False),
        sa.Column("rfp_text", sa.Text(), nullable=False),
        sa.Column("eligibility", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("proposal_text", sa.Text()), sa.Column("status", sa.String(20), nullable=False, server_default="analyzed"),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")), created_at(),
    )
    op.create_index("idx_rfp_bids_org", "rfp_bids", ["org_id"])

    op.create_table(
        "user_activity_log", *base_columns(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        client_column(nullable=True), sa.Column("activity_type", sa.String(40), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")), created_at(),
    )
    op.create_index("idx_user_activity_log_org", "user_activity_log", ["org_id"])

    op.create_table(
        "timesheet_entries", *base_columns(),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        client_column(), sa.Column("date", sa.Date(), nullable=False),
        sa.Column("hours_logged", sa.Numeric(5, 2), nullable=False), sa.Column("task_description", sa.Text(), nullable=False),
        sa.Column("billable", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("billing_rate", sa.Numeric(10, 2), nullable=False, server_default="1500"),
        sa.Column("cost_rate", sa.Numeric(10, 2), nullable=False, server_default="800"), created_at(),
    )
    op.create_index("idx_timesheet_entries_org", "timesheet_entries", ["org_id"])

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )


def downgrade():
    for table in reversed(TENANT_TABLES):
        op.drop_table(table)
    op.drop_constraint("ck_documents_doc_type", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_doc_type", "documents",
        "doc_type IN ('invoice','gstr2b','purchase_register','notice','trial_balance','bank_statement')",
    )
    op.drop_column("clients", "registered_office")
    op.drop_column("clients", "cin")
    op.drop_column("clients", "entity_type")
