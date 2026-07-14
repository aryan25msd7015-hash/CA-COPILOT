"""initial schema

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

Full DDL for all 13 tables in the CA Intelligence Platform.
Includes all indexes, CHECK constraints, FK constraints, and the
pgvector IVFFlat index on legal_chunks.embedding.
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


def upgrade() -> None:
    # ──────────────────────────────────────────────────────────────
    # Extensions (idempotent — safe to run multiple times)
    # ──────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS pg_trgm')

    # ──────────────────────────────────────────────────────────────
    # organizations — root tenant table (no org_id FK)
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "plan",
            sa.String(20),
            nullable=False,
            server_default="starter",
        ),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    # ──────────────────────────────────────────────────────────────
    # users
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), unique=True, nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('partner','manager','article')",
            name="ck_users_role",
        ),
    )
    op.create_index("idx_users_org", "users", ["org_id"])

    # ──────────────────────────────────────────────────────────────
    # clients
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "clients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("whatsapp_number", sa.String(20), nullable=True),
        sa.Column("whatsapp_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("industry", sa.String(50), nullable=True),
        sa.Column("benchmark_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_clients_org", "clients", ["org_id"])

    # ──────────────────────────────────────────────────────────────
    # documents
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(30), nullable=False),
        sa.Column("s3_key", sa.Text(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("ocr_json", postgresql.JSONB(), nullable=True),
        sa.Column(
            "source",
            sa.String(10),
            nullable=False,
            server_default="upload",
        ),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("celery_task_id", sa.String(50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "doc_type IN ('invoice','gstr2b','purchase_register','notice','trial_balance','bank_statement')",
            name="ck_documents_doc_type",
        ),
        sa.CheckConstraint(
            "source IN ('upload','whatsapp')",
            name="ck_documents_source",
        ),
        sa.CheckConstraint(
            "status IN ('pending','ocr_complete','ocr_failed','parse_failed','processed')",
            name="ck_documents_status",
        ),
    )
    op.create_index("idx_documents_org", "documents", ["org_id"])
    op.create_index("idx_documents_client", "documents", ["client_id"])
    op.create_index("idx_documents_status", "documents", ["status"])

    # ──────────────────────────────────────────────────────────────
    # transactions
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("invoice_no", sa.Text(), nullable=True),
        sa.Column("vendor_gstin", sa.String(15), nullable=True),
        sa.Column("vendor_name", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("tax_amount", sa.Numeric(15, 2), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column(
            "match_status",
            sa.String(15),
            nullable=False,
            server_default="unmatched",
        ),
        sa.Column("match_confidence", sa.Numeric(5, 2), nullable=True),
        sa.Column("anomaly_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("fraud_flag", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column(
            "source",
            sa.String(10),
            nullable=False,
            server_default="upload",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "match_status IN ('unmatched','exact','tolerance','fuzzy')",
            name="ck_transactions_match_status",
        ),
    )
    op.create_index("idx_transactions_org", "transactions", ["org_id"])
    op.create_index("idx_transactions_client", "transactions", ["client_id"])
    op.create_index("idx_transactions_vendor", "transactions", ["vendor_gstin"])
    op.create_index("idx_transactions_date", "transactions", ["date"])
    op.create_index("idx_transactions_fingerprint", "transactions", ["fingerprint"])

    # ──────────────────────────────────────────────────────────────
    # legal_chunks — shared knowledge base (no org_id)
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "legal_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("doc_type", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "doc_type IN ('income_tax_act','gst_act','circular','reply_template')",
            name="ck_legal_chunks_doc_type",
        ),
    )
    # IVFFlat cosine similarity index for fast ANN search
    # Must be created after the table exists and ideally after data is loaded,
    # but we include it here as part of the schema baseline.
    op.execute(
        """
        CREATE INDEX idx_legal_chunks_embedding
        ON legal_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )

    # ──────────────────────────────────────────────────────────────
    # compliance_deadlines
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "compliance_deadlines",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filing_type", sa.String(20), nullable=False),
        sa.Column("filing_name", sa.Text(), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doc_required", sa.String(30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','filed','missed')",
            name="ck_deadlines_status",
        ),
    )
    op.create_index("idx_deadlines_org", "compliance_deadlines", ["org_id"])
    op.create_index("idx_deadlines_client", "compliance_deadlines", ["client_id"])
    op.create_index("idx_deadlines_date", "compliance_deadlines", ["deadline"])

    # ──────────────────────────────────────────────────────────────
    # whatsapp_reminders
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "whatsapp_reminders",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "deadline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("compliance_deadlines.id"),
            nullable=True,
        ),
        sa.Column("template", sa.String(50), nullable=False),
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="sent",
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('sent','failed')",
            name="ck_wa_reminders_status",
        ),
    )
    op.create_index("idx_wa_reminders_client", "whatsapp_reminders", ["client_id"])

    # ──────────────────────────────────────────────────────────────
    # reconciliation_config
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "reconciliation_config",
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "amount_tolerance",
            sa.Numeric(10, 2),
            nullable=False,
            server_default="5",
        ),
        sa.Column("date_tolerance", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("fuzzy_threshold", sa.Integer(), nullable=False, server_default="85"),
    )

    # ──────────────────────────────────────────────────────────────
    # reconciliation_results
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "reconciliation_results",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("total_purchase", sa.Numeric(15, 2), nullable=True),
        sa.Column("total_gstr2b", sa.Numeric(15, 2), nullable=True),
        sa.Column("matched_count", sa.Integer(), nullable=True),
        sa.Column("unmatched_count", sa.Integer(), nullable=True),
        sa.Column("mismatch_value", sa.Numeric(15, 2), nullable=True),
        sa.Column(
            "run_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_recon_results_client", "reconciliation_results", ["client_id"])

    # ──────────────────────────────────────────────────────────────
    # client_health_history
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "client_health_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("tier", sa.String(10), nullable=False),
        sa.Column("components", postgresql.JSONB(), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tier IN ('green','amber','red')",
            name="ck_health_history_tier",
        ),
    )
    op.create_index("idx_health_history_client", "client_health_history", ["client_id"])

    # ──────────────────────────────────────────────────────────────
    # anomaly_flags
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "anomaly_flags",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "transaction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("transactions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("flag_type", sa.String(30), nullable=False),
        sa.Column("risk_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column(
            "reviewed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_anomaly_flags_client", "anomaly_flags", ["client_id"])

    # ──────────────────────────────────────────────────────────────
    # saved_queries
    # ──────────────────────────────────────────────────────────────
    op.create_table(
        "saved_queries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("nl_query", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index("idx_saved_queries_user", "saved_queries", ["user_id"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_index("idx_saved_queries_user", table_name="saved_queries")
    op.drop_table("saved_queries")

    op.drop_index("idx_anomaly_flags_client", table_name="anomaly_flags")
    op.drop_table("anomaly_flags")

    op.drop_index("idx_health_history_client", table_name="client_health_history")
    op.drop_table("client_health_history")

    op.drop_index("idx_recon_results_client", table_name="reconciliation_results")
    op.drop_table("reconciliation_results")

    op.drop_table("reconciliation_config")

    op.drop_index("idx_wa_reminders_client", table_name="whatsapp_reminders")
    op.drop_table("whatsapp_reminders")

    op.drop_index("idx_deadlines_date", table_name="compliance_deadlines")
    op.drop_index("idx_deadlines_client", table_name="compliance_deadlines")
    op.drop_index("idx_deadlines_org", table_name="compliance_deadlines")
    op.drop_table("compliance_deadlines")

    op.execute("DROP INDEX IF EXISTS idx_legal_chunks_embedding")
    op.drop_table("legal_chunks")

    op.drop_index("idx_transactions_fingerprint", table_name="transactions")
    op.drop_index("idx_transactions_date", table_name="transactions")
    op.drop_index("idx_transactions_vendor", table_name="transactions")
    op.drop_index("idx_transactions_client", table_name="transactions")
    op.drop_index("idx_transactions_org", table_name="transactions")
    op.drop_table("transactions")

    op.drop_index("idx_documents_status", table_name="documents")
    op.drop_index("idx_documents_client", table_name="documents")
    op.drop_index("idx_documents_org", table_name="documents")
    op.drop_table("documents")

    op.drop_index("idx_clients_org", table_name="clients")
    op.drop_table("clients")

    op.drop_index("idx_users_org", table_name="users")
    op.drop_table("users")

    op.drop_table("organizations")
