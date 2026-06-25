"""Practice operations models for office management, billing, portal, and reports."""
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
    UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


def _id():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org():
    return Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


def _client(nullable=True):
    return Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
    )


def _user(nullable=True):
    return Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=nullable,
        index=True,
    )


def _created_at():
    return Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PracticeTask(Base):
    __tablename__ = "practice_tasks"
    __table_args__ = (
        Index("idx_practice_tasks_org_status_due", "org_id", "status", "due_date"),
        Index("idx_practice_tasks_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    title = Column(Text, nullable=False)
    service_type = Column(String(40), nullable=False, default="compliance")
    priority = Column(String(10), nullable=False, default="medium")
    status = Column(String(20), nullable=False, default="open", index=True)
    stage = Column(String(30), nullable=False, default="maker")
    due_date = Column(Date, index=True)
    assigned_to = _user()
    reviewer_id = _user()
    checklist = Column(JSONB, nullable=False, default=list)
    tags = Column(JSONB, nullable=False, default=list)
    recurring_rule = Column(JSONB, nullable=False, default=dict)
    notes = Column(Text)
    created_by = _user()
    completed_at = Column(DateTime(timezone=True))
    created_at = _created_at()
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class DaybookEntry(Base):
    __tablename__ = "daybook_entries"
    __table_args__ = (
        Index("idx_daybook_org_date_created", "org_id", "entry_date", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    task_id = Column(UUID(as_uuid=True), ForeignKey("practice_tasks.id", ondelete="SET NULL"), index=True)
    entry_date = Column(Date, nullable=False, index=True)
    activity_type = Column(String(40), nullable=False, default="follow_up")
    summary = Column(Text, nullable=False)
    assigned_to = _user()
    status = Column(String(20), nullable=False, default="open")
    created_by = _user()
    created_at = _created_at()


class BillingPlan(Base):
    __tablename__ = "billing_plans"
    __table_args__ = (
        Index("idx_billing_plans_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    name = Column(Text, nullable=False)
    service_scope = Column(JSONB, nullable=False, default=list)
    frequency = Column(String(20), nullable=False, default="monthly")
    amount = Column(Numeric(15, 2), nullable=False, default=0)
    tax_rate = Column(Numeric(5, 2), nullable=False, default=18)
    next_invoice_date = Column(Date)
    active = Column(Boolean, nullable=False, default=True)
    created_at = _created_at()


class PracticeInvoice(Base):
    __tablename__ = "practice_invoices"
    __table_args__ = (
        UniqueConstraint("org_id", "invoice_no", name="uq_practice_invoice_no"),
        Index("idx_practice_invoices_org_status_due", "org_id", "status", "due_date"),
        Index("idx_practice_invoices_org_client_due", "org_id", "client_id", "due_date"),
    )

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("billing_plans.id", ondelete="SET NULL"), index=True)
    invoice_no = Column(String(40), nullable=False)
    issue_date = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    line_items = Column(JSONB, nullable=False, default=list)
    subtotal = Column(Numeric(15, 2), nullable=False, default=0)
    tax = Column(Numeric(15, 2), nullable=False, default=0)
    total = Column(Numeric(15, 2), nullable=False, default=0)
    amount_paid = Column(Numeric(15, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="draft", index=True)
    payment_link = Column(Text)
    created_by = _user()
    created_at = _created_at()


class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"

    id = _id()
    org_id = _org()
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("practice_invoices.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = _client(nullable=False)
    paid_at = Column(Date, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    mode = Column(String(30), nullable=False, default="bank_transfer")
    reference = Column(Text)
    notes = Column(Text)
    created_by = _user()
    created_at = _created_at()


class ClientPortalContact(Base):
    __tablename__ = "client_portal_contacts"
    __table_args__ = (
        UniqueConstraint("client_id", "email", name="uq_portal_contact_email"),
        Index("idx_portal_contacts_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    name = Column(Text, nullable=False)
    email = Column(Text, nullable=False)
    phone = Column(String(20))
    role = Column(String(40), nullable=False, default="client_user")
    access_status = Column(String(20), nullable=False, default="invited")
    last_login_at = Column(DateTime(timezone=True))
    created_at = _created_at()


class PortalRequest(Base):
    __tablename__ = "portal_requests"
    __table_args__ = (
        Index("idx_portal_requests_org_status_due", "org_id", "status", "due_date"),
        Index("idx_portal_requests_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("client_portal_contacts.id", ondelete="SET NULL"), index=True)
    request_type = Column(String(30), nullable=False, default="document")
    title = Column(Text, nullable=False)
    description = Column(Text)
    due_date = Column(Date, index=True)
    status = Column(String(20), nullable=False, default="requested", index=True)
    attachments = Column(JSONB, nullable=False, default=list)
    response_summary = Column(Text)
    created_by = _user()
    created_at = _created_at()
    completed_at = Column(DateTime(timezone=True))


class AttendanceEntry(Base):
    __tablename__ = "attendance_entries"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", "work_date", name="uq_attendance_user_date"),
        Index("idx_attendance_org_date", "org_id", "work_date"),
    )

    id = _id()
    org_id = _org()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    work_date = Column(Date, nullable=False, index=True)
    status = Column(String(20), nullable=False, default="present")
    hours_available = Column(Numeric(5, 2), nullable=False, default=8)
    hours_booked = Column(Numeric(5, 2), nullable=False, default=0)
    notes = Column(Text)
    created_at = _created_at()


class CredentialVaultItem(Base):
    __tablename__ = "credential_vault_items"
    __table_args__ = (
        Index("idx_vault_items_org_client_expires", "org_id", "client_id", "expires_on"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    label = Column(Text, nullable=False)
    credential_type = Column(String(30), nullable=False, default="portal")
    username = Column(Text)
    masked_secret = Column(Text)
    storage_reference = Column(Text)
    owner_user_id = _user()
    expires_on = Column(Date, index=True)
    rotation_status = Column(String(20), nullable=False, default="current")
    last_used_at = Column(DateTime(timezone=True))
    notes = Column(Text)
    created_by = _user()
    created_at = _created_at()


class ImportJob(Base):
    __tablename__ = "import_jobs"
    __table_args__ = (
        Index("idx_import_jobs_org_status_created", "org_id", "status", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    import_type = Column(String(40), nullable=False)
    source_name = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    mapping = Column(JSONB, nullable=False, default=dict)
    sample_rows = Column(JSONB, nullable=False, default=list)
    validation_errors = Column(JSONB, nullable=False, default=list)
    records_total = Column(Integer, nullable=False, default=0)
    records_valid = Column(Integer, nullable=False, default=0)
    records_imported = Column(Integer, nullable=False, default=0)
    created_by = _user()
    created_at = _created_at()
    completed_at = Column(DateTime(timezone=True))


class SavedView(Base):
    __tablename__ = "saved_views"
    __table_args__ = (
        Index("idx_saved_views_org_user_created", "org_id", "user_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    user_id = _user(nullable=False)
    name = Column(Text, nullable=False)
    view_type = Column(String(40), nullable=False, default="report")
    filters = Column(JSONB, nullable=False, default=dict)
    columns = Column(JSONB, nullable=False, default=list)
    is_shared = Column(Boolean, nullable=False, default=False)
    created_at = _created_at()
