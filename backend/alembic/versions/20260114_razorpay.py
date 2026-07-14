"""razorpay events and subscriptions

Revision ID: 20260114_razorpay
Revises: 
Create Date: 2026-01-14

Applies two new tables required by the Razorpay integration:

    razorpay_events            -> webhook receipts (idempotent, replay-safe)
    razorpay_subscriptions     -> firm-level CA Copilot SaaS subscriptions

The one-time invoice payment flow reuses the existing invoices / invoice_payments
tables in app/models/practice_ops.py; no schema change there.

To apply:
    docker compose exec backend alembic upgrade head
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260114_razorpay"
down_revision = None  # ← adjust to your previous head before applying
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "razorpay_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("razorpay_plan_id", sa.String(64), nullable=False),
        sa.Column("razorpay_subscription_id", sa.String(64), nullable=False, unique=True),
        sa.Column("plan_code", sa.String(32), nullable=False),
        sa.Column("plan_period", sa.String(16), nullable=False, server_default="monthly"),
        sa.Column("amount_inr", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="INR"),
        sa.Column("status", sa.String(24), nullable=False, server_default="created"),
        sa.Column("current_start", sa.DateTime(timezone=True)),
        sa.Column("current_end", sa.DateTime(timezone=True)),
        sa.Column("next_charge_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("short_url", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_razorpay_subs_status", "razorpay_subscriptions", ["status"])

    op.create_table(
        "razorpay_events",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("razorpay_event_id", sa.String(64), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False, index=True),
        sa.Column("signature_ok", sa.String(8), nullable=False, server_default="true"),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("razorpay_order_id", sa.String(64)),
        sa.Column("razorpay_payment_id", sa.String(64)),
        sa.Column("razorpay_payment_link_id", sa.String(64)),
        sa.Column("razorpay_subscription_id", sa.String(64)),
        sa.Column("razorpay_refund_id", sa.String(64)),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("razorpay_subscriptions.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        sa.Column("handle_error", sa.String(500)),
        sa.UniqueConstraint("razorpay_event_id", name="uq_razorpay_event_id"),
    )
    op.create_index("ix_razorpay_events_order", "razorpay_events", ["razorpay_order_id"])
    op.create_index("ix_razorpay_events_payment", "razorpay_events", ["razorpay_payment_id"])
    op.create_index("ix_razorpay_events_sub", "razorpay_events", ["razorpay_subscription_id"])


def downgrade() -> None:
    op.drop_table("razorpay_events")
    op.drop_table("razorpay_subscriptions")
