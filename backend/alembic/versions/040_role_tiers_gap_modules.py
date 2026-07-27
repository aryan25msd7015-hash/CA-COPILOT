"""Gap modules + portal auth tokens for four-tier RBAC expansion.

Revision ID: 040
Revises: 039
Create Date: 2026-07-27 18:45:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())
UUID = postgresql.UUID(as_uuid=True)

TENANT_TABLES = [
    "litigation_cases",
    "engagement_onboardings",
    "tds_recon_runs",
    "audit_observations",
    "statutory_checklists",
    "peer_review_packs",
    "knowledge_articles",
    "roc_xbrl_filings",
    "einvoice_validations",
    "client_risk_scores",
    "mis_dashboards",
    "portal_auth_tokens",
]


def upgrade() -> None:
    op.create_table(
        "litigation_cases",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("forum", sa.String(40), nullable=False, server_default="CIT(A)"),
        sa.Column("case_no", sa.String(80), nullable=False),
        sa.Column("ay_or_period", sa.String(20)),
        sa.Column("matter_summary", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="open"),
        sa.Column("next_hearing_date", sa.Date()),
        sa.Column("submission_due", sa.Date()),
        sa.Column("counsel_name", sa.Text()),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("meta", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_litigation_org_status", "litigation_cases", ["org_id", "status"])
    op.create_index("ix_litigation_cases_org_id", "litigation_cases", ["org_id"])
    op.create_index("ix_litigation_cases_client_id", "litigation_cases", ["client_id"])

    op.create_table(
        "engagement_onboardings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_type", sa.String(40), nullable=False, server_default="statutory_audit"),
        sa.Column("risk_category", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("kyc_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("aml_flags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("letter_status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("udin", sa.String(40)),
        sa.Column("letter_body", sa.Text()),
        sa.Column("documents", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("approved_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_engagement_org_status", "engagement_onboardings", ["org_id", "status"])
    op.create_index("ix_engagement_onboardings_org_id", "engagement_onboardings", ["org_id"])
    op.create_index("ix_engagement_onboardings_client_id", "engagement_onboardings", ["client_id"])

    op.create_table(
        "tds_recon_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("source", sa.String(20), nullable=False, server_default="26AS"),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("books_total", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("portal_total", sa.Numeric(15, 2), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Numeric(10, 0), nullable=False, server_default="0"),
        sa.Column("exception_count", sa.Numeric(10, 0), nullable=False, server_default="0"),
        sa.Column("exceptions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_tds_recon_org_period", "tds_recon_runs", ["org_id", "period"])
    op.create_index("ix_tds_recon_runs_org_id", "tds_recon_runs", ["org_id"])
    op.create_index("ix_tds_recon_runs_client_id", "tds_recon_runs", ["client_id"])

    op.create_table(
        "audit_observations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engagement_ref", sa.String(80)),
        sa.Column("area", sa.String(80), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("raised_to", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("response_text", sa.Text()),
        sa.Column("due_date", sa.Date()),
        sa.Column("raised_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("closed_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_observations_org_status", "audit_observations", ["org_id", "status"])
    op.create_index("ix_audit_observations_org_id", "audit_observations", ["org_id"])
    op.create_index("ix_audit_observations_client_id", "audit_observations", ["client_id"])

    op.create_table(
        "statutory_checklists",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("framework", sa.String(40), nullable=False, server_default="CARO"),
        sa.Column("entity_type", sa.String(40), nullable=False, server_default="pvt_ltd"),
        sa.Column("fy", sa.String(20), nullable=False),
        sa.Column("items", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("completion_pct", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.Column("signed_off_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("signed_off_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_checklists_org_client", "statutory_checklists", ["org_id", "client_id"])
    op.create_index("ix_statutory_checklists_org_id", "statutory_checklists", ["org_id"])
    op.create_index("ix_statutory_checklists_client_id", "statutory_checklists", ["client_id"])

    op.create_table(
        "peer_review_packs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_label", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("checklist", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("evidence_links", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("readiness_score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("owner_user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_peer_review_org", "peer_review_packs", ["org_id"])
    op.create_index("ix_peer_review_packs_org_id", "peer_review_packs", ["org_id"])

    op.create_table(
        "knowledge_articles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(80), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("tags", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_knowledge_org_topic", "knowledge_articles", ["org_id", "topic"])
    op.create_index("ix_knowledge_articles_org_id", "knowledge_articles", ["org_id"])

    op.create_table(
        "roc_xbrl_filings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("form_name", sa.String(40), nullable=False),
        sa.Column("fy", sa.String(20), nullable=False),
        sa.Column("due_date", sa.Date()),
        sa.Column("validation_status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("cost_audit_applicable", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("notes", sa.Text()),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_roc_xbrl_org_due", "roc_xbrl_filings", ["org_id", "due_date"])
    op.create_index("ix_roc_xbrl_filings_org_id", "roc_xbrl_filings", ["org_id"])
    op.create_index("ix_roc_xbrl_filings_client_id", "roc_xbrl_filings", ["client_id"])

    op.create_table(
        "einvoice_validations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invoice_no", sa.String(60), nullable=False),
        sa.Column("irn", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("turnover_threshold_hit", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("details", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_einvoice_org_client", "einvoice_validations", ["org_id", "client_id"])
    op.create_index("ix_einvoice_validations_org_id", "einvoice_validations", ["org_id"])
    op.create_index("ix_einvoice_validations_client_id", "einvoice_validations", ["client_id"])

    op.create_table(
        "client_risk_scores",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("tier", sa.String(10), nullable=False, server_default="green"),
        sa.Column("drivers", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "client_id", name="uq_client_risk_score"),
    )
    op.create_index("idx_client_risk_org_score", "client_risk_scores", ["org_id", "score"])
    op.create_index("ix_client_risk_scores_org_id", "client_risk_scores", ["org_id"])
    op.create_index("ix_client_risk_scores_client_id", "client_risk_scores", ["client_id"])

    op.create_table(
        "mis_dashboards",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("metrics", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("narrative", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_mis_org_client_period", "mis_dashboards", ["org_id", "client_id", "period"])
    op.create_index("ix_mis_dashboards_org_id", "mis_dashboards", ["org_id"])
    op.create_index("ix_mis_dashboards_client_id", "mis_dashboards", ["client_id"])

    op.create_table(
        "portal_auth_tokens",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("org_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", UUID, sa.ForeignKey("client_portal_contacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_portal_auth_token_hash", "portal_auth_tokens", ["token_hash"])
    op.create_index("ix_portal_auth_tokens_org_id", "portal_auth_tokens", ["org_id"])
    op.create_index("ix_portal_auth_tokens_client_id", "portal_auth_tokens", ["client_id"])

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_tenant_policy ON {table} "
            "USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            "WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )


def downgrade() -> None:
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        op.drop_table(table)
