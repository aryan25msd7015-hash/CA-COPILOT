"""Harden practice operations indexes.

Revision ID: 017
Revises: 016
Create Date: 2026-06-19
"""

from alembic import op


revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("idx_practice_tasks_org_status_due", "practice_tasks", ["org_id", "status", "due_date"])
    op.create_index("idx_practice_tasks_org_client_created", "practice_tasks", ["org_id", "client_id", "created_at"])
    op.create_index("idx_daybook_org_date_created", "daybook_entries", ["org_id", "entry_date", "created_at"])
    op.create_index("idx_billing_plans_org_client_created", "billing_plans", ["org_id", "client_id", "created_at"])
    op.create_index("idx_practice_invoices_org_status_due", "practice_invoices", ["org_id", "status", "due_date"])
    op.create_index("idx_practice_invoices_org_client_due", "practice_invoices", ["org_id", "client_id", "due_date"])
    op.create_index("idx_portal_contacts_org_client_created", "client_portal_contacts", ["org_id", "client_id", "created_at"])
    op.create_index("idx_portal_requests_org_status_due", "portal_requests", ["org_id", "status", "due_date"])
    op.create_index("idx_portal_requests_org_client_created", "portal_requests", ["org_id", "client_id", "created_at"])
    op.create_index("idx_attendance_org_date", "attendance_entries", ["org_id", "work_date"])
    op.create_index("idx_vault_items_org_client_expires", "credential_vault_items", ["org_id", "client_id", "expires_on"])
    op.create_index("idx_import_jobs_org_status_created", "import_jobs", ["org_id", "status", "created_at"])
    op.create_index("idx_saved_views_org_user_created", "saved_views", ["org_id", "user_id", "created_at"])


def downgrade():
    op.drop_index("idx_saved_views_org_user_created", table_name="saved_views")
    op.drop_index("idx_import_jobs_org_status_created", table_name="import_jobs")
    op.drop_index("idx_vault_items_org_client_expires", table_name="credential_vault_items")
    op.drop_index("idx_attendance_org_date", table_name="attendance_entries")
    op.drop_index("idx_portal_requests_org_client_created", table_name="portal_requests")
    op.drop_index("idx_portal_requests_org_status_due", table_name="portal_requests")
    op.drop_index("idx_portal_contacts_org_client_created", table_name="client_portal_contacts")
    op.drop_index("idx_practice_invoices_org_client_due", table_name="practice_invoices")
    op.drop_index("idx_practice_invoices_org_status_due", table_name="practice_invoices")
    op.drop_index("idx_billing_plans_org_client_created", table_name="billing_plans")
    op.drop_index("idx_daybook_org_date_created", table_name="daybook_entries")
    op.drop_index("idx_practice_tasks_org_client_created", table_name="practice_tasks")
    op.drop_index("idx_practice_tasks_org_status_due", table_name="practice_tasks")
