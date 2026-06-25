"""WhatsApp reminder status metadata.

Revision ID: 028
Revises: 027
Create Date: 2026-06-23 04:58:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("whatsapp_reminders", sa.Column("channel", sa.String(length=20), nullable=False, server_default="whatsapp"))
    op.add_column("whatsapp_reminders", sa.Column("provider_message_id", sa.String(length=100), nullable=True))
    op.add_column(
        "whatsapp_reminders",
        sa.Column("provider_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column("whatsapp_reminders", sa.Column("error_message", sa.String(length=500), nullable=True))
    op.create_index(
        "idx_wa_reminders_org_status_sent",
        "whatsapp_reminders",
        ["org_id", "status", "sent_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_wa_reminders_org_status_sent", table_name="whatsapp_reminders")
    op.drop_column("whatsapp_reminders", "error_message")
    op.drop_column("whatsapp_reminders", "provider_response")
    op.drop_column("whatsapp_reminders", "provider_message_id")
    op.drop_column("whatsapp_reminders", "channel")
