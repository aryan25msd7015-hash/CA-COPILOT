"""email_events and email_sends tables

Revision ID: 20260114_email
Revises: 20260114_razorpay
Create Date: 2026-01-14

Adds two new tables required by the Resend integration:

    email_sends   -> one row per outbound send attempt
    email_events  -> one row per Svix webhook event, deduped by svix-id

Also adds `email_bounced_at` on `users` so we can stop sending to a recipient
that hard-bounced. All new columns are nullable to avoid touching existing rows.

To apply:
    docker compose exec backend alembic upgrade head
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260114_email"
down_revision = "20260114_razorpay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_sends",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("resend_message_id", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="queued"),
        sa.Column("dry_run", sa.String(8), nullable=False, server_default="false"),
        sa.Column("error", sa.String(500)),
        sa.Column("tags", postgresql.JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_sends_message", "email_sends", ["resend_message_id"])
    op.create_index("ix_email_sends_org_template", "email_sends", ["org_id", "template"])

    op.create_table(
        "email_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("resend_event_id", sa.String(64)),
        sa.Column("resend_message_id", sa.String(64)),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("recipient", sa.String(255)),
        sa.Column("template", sa.String(64)),
        sa.Column("tags", postgresql.JSONB),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("signature_ok", sa.String(8), nullable=False, server_default="true"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        sa.Column("handle_error", sa.String(500)),
        sa.UniqueConstraint("resend_event_id", name="uq_email_event_id"),
    )
    op.create_index("ix_email_events_type", "email_events", ["event_type"])
    op.create_index("ix_email_events_message", "email_events", ["resend_message_id"])
    op.create_index("ix_email_events_recipient", "email_events", ["recipient"])

    op.add_column("users", sa.Column("email_bounced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "email_bounced_at")
    op.drop_table("email_events")
    op.drop_table("email_sends")
