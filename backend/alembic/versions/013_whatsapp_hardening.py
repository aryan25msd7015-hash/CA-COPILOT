"""Harden WhatsApp module indexes.

Revision ID: 013
Revises: 012
Create Date: 2026-06-19
"""

from alembic import op


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_wa_reminders_org_client_sent", "whatsapp_reminders", ["org_id", "client_id", "sent_at"])
    op.create_index("idx_wa_reminders_org_deadline", "whatsapp_reminders", ["org_id", "deadline_id"])


def downgrade():
    op.drop_index("idx_wa_reminders_org_deadline", table_name="whatsapp_reminders")
    op.drop_index("idx_wa_reminders_org_client_sent", table_name="whatsapp_reminders")
