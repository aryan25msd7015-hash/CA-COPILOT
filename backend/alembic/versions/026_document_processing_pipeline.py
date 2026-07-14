"""Document processing pipeline metadata.

Revision ID: 026
Revises: 025
Create Date: 2026-06-23 01:42:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending_upload','received','pending','processing','ocr_complete','ocr_failed','parse_failed','failed_validation','verified','processed')",
    )
    op.add_column("documents", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("documents", sa.Column("last_pipeline_error_type", sa.String(length=60), nullable=True))

    op.create_table(
        "document_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("supplier_name", sa.Text(), nullable=True),
        sa.Column("supplier_gstin", sa.String(length=15), nullable=True),
        sa.Column("invoice_number", sa.Text(), nullable=True),
        sa.Column("invoice_date", sa.String(length=30), nullable=True),
        sa.Column("taxable_value", sa.String(length=30), nullable=True),
        sa.Column("cgst_amount", sa.String(length=30), nullable=True),
        sa.Column("sgst_amount", sa.String(length=30), nullable=True),
        sa.Column("igst_amount", sa.String(length=30), nullable=True),
        sa.Column("total_amount", sa.String(length=30), nullable=True),
        sa.Column("confidence_score", sa.String(length=20), nullable=True),
        sa.Column("validation_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("validation_errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("auto_tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("raw_extracted_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_document_extractions_org_client_created", "document_extractions", ["org_id", "client_id", "created_at"])
    op.create_index("idx_document_extractions_org_supplier", "document_extractions", ["org_id", "supplier_gstin"])

    op.create_table(
        "document_pipeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_type", sa.String(length=60), nullable=True),
        sa.Column("diagnostic_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_document_pipeline_events_org_doc_created", "document_pipeline_events", ["org_id", "document_id", "created_at"])

    for table in ("document_extractions", "document_pipeline_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
            WITH CHECK (org_id = nullif(current_setting('app.current_org_id', true), '')::uuid)
            """
        )


def downgrade() -> None:
    for table in ("document_pipeline_events", "document_extractions"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_index("idx_document_pipeline_events_org_doc_created", table_name="document_pipeline_events")
    op.drop_table("document_pipeline_events")
    op.drop_index("idx_document_extractions_org_supplier", table_name="document_extractions")
    op.drop_index("idx_document_extractions_org_client_created", table_name="document_extractions")
    op.drop_table("document_extractions")
    op.drop_column("documents", "last_pipeline_error_type")
    op.drop_column("documents", "processing_completed_at")
    op.drop_column("documents", "processing_started_at")
    op.drop_constraint("ck_documents_status", "documents", type_="check")
    op.create_check_constraint(
        "ck_documents_status",
        "documents",
        "status IN ('pending_upload','received','pending','ocr_complete','ocr_failed','parse_failed','processed')",
    )
