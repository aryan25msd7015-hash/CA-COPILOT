"""Hybrid Audit Engine schema: fused risk columns + model registry tables.

Revision ID: 037
Revises: 036
Create Date: 2026-07-27 16:40:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("audit_risk_score", sa.Numeric(6, 2), nullable=True))
    op.add_column("transactions", sa.Column("audit_risk_prob", sa.Numeric(5, 4), nullable=True))
    op.add_column("transactions", sa.Column("audit_risk_drivers", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("transactions", sa.Column("hae_layer_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("idx_transactions_org_audit_risk", "transactions", ["org_id", "audit_risk_score"])

    op.create_table(
        "audit_model_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False, server_default="latest"),
        sa.Column("backend", sa.String(length=30), nullable=False, server_default="sklearn"),
        sa.Column("local_path", sa.Text(), nullable=True),
        sa.Column("s3_key", sa.Text(), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_audit_model_artifacts_org_name", "audit_model_artifacts", ["org_id", "name"])
    op.create_index("idx_audit_model_artifacts_org_active", "audit_model_artifacts", ["org_id", "is_active"])

    op.create_table(
        "audit_engine_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id", ondelete="CASCADE"), nullable=True),
        sa.Column("run_type", sa.String(length=40), nullable=False, server_default="score"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_audit_engine_runs_org_created", "audit_engine_runs", ["org_id", "created_at"])
    op.create_index("idx_audit_engine_runs_org_client", "audit_engine_runs", ["org_id", "client_id"])

    op.create_table(
        "audit_bandit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_id", sa.String(length=80), nullable=True),
        sa.Column("arm", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reward", sa.Numeric(6, 4), nullable=True),
        sa.Column("review_status", sa.String(length=30), nullable=True),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("idx_audit_bandit_events_org_created", "audit_bandit_events", ["org_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_audit_bandit_events_org_created", table_name="audit_bandit_events")
    op.drop_table("audit_bandit_events")
    op.drop_index("idx_audit_engine_runs_org_client", table_name="audit_engine_runs")
    op.drop_index("idx_audit_engine_runs_org_created", table_name="audit_engine_runs")
    op.drop_table("audit_engine_runs")
    op.drop_index("idx_audit_model_artifacts_org_active", table_name="audit_model_artifacts")
    op.drop_index("idx_audit_model_artifacts_org_name", table_name="audit_model_artifacts")
    op.drop_table("audit_model_artifacts")
    op.drop_index("idx_transactions_org_audit_risk", table_name="transactions")
    op.drop_column("transactions", "hae_layer_scores")
    op.drop_column("transactions", "audit_risk_drivers")
    op.drop_column("transactions", "audit_risk_prob")
    op.drop_column("transactions", "audit_risk_score")
