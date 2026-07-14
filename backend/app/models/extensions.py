"""Operational models for the advanced automation modules."""
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    Index, UniqueConstraint, func,
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


def _client(nullable=False):
    return Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=nullable,
        index=True,
    )


class DeadlineClientMap(Base):
    __tablename__ = "deadline_client_map"
    __table_args__ = (
        UniqueConstraint("client_id", "filing_type", "period", name="uq_deadline_client_period"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    filing_type = Column(String(30), nullable=False)
    filing_name = Column(Text, nullable=False)
    period = Column(String(20), nullable=False)
    deadline = Column(Date, nullable=False, index=True)
    data_received = Column(Boolean, nullable=False, default=False)
    data_received_at = Column(DateTime(timezone=True))
    data_source = Column(String(20))
    status = Column(String(10), nullable=False, default="pending")
    filed_at = Column(DateTime(timezone=True))
    late_count_last_12m = Column(Integer, nullable=False, default=0)
    has_open_notice = Column(Boolean, nullable=False, default=False)
    risk_score = Column(Numeric(4, 1), nullable=False, default=0)
    reminders_sent = Column(Integer, nullable=False, default=0)
    last_reminder_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MsmeVendor(Base):
    __tablename__ = "msme_vendors"
    __table_args__ = (
        UniqueConstraint("client_id", "vendor_gstin", name="uq_msme_vendor_client_gstin"),
        Index("idx_msme_vendors_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    vendor_gstin = Column(String(15))
    vendor_name = Column(Text, nullable=False)
    udyam_reg_no = Column(String(30))
    udyam_category = Column(String(10), nullable=False)
    udyam_cert_doc_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"))
    registered_at = Column(Date)
    verified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MsmePaymentViolation(Base):
    __tablename__ = "msme_payment_violations"
    __table_args__ = (
        UniqueConstraint("vendor_id", "invoice_id", name="uq_msme_violation_invoice"),
        Index("idx_msme_violations_org_client_fy", "org_id", "client_id", "fy"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("msme_vendors.id", ondelete="CASCADE"), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False)
    invoice_date = Column(Date, nullable=False)
    invoice_amount = Column(Numeric(15, 2), nullable=False)
    due_date = Column(Date, nullable=False)
    payment_date = Column(Date)
    days_overdue = Column(Integer, nullable=False)
    disallowance_amount = Column(Numeric(15, 2), nullable=False)
    interest_amount = Column(Numeric(15, 2), nullable=False)
    fy = Column(String(10), nullable=False)
    status = Column(String(10), nullable=False, default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BankFacility(Base):
    __tablename__ = "bank_facilities"
    __table_args__ = (
        Index("idx_bank_facilities_org_client", "org_id", "client_id"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    bank_name = Column(Text, nullable=False)
    facility_type = Column(String(10), nullable=False, default="CC")
    sanctioned_limit = Column(Numeric(15, 2), nullable=False)
    margin_rules = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = _id()
    org_id = _org()
    client_id = _client()
    period = Column(String(20), nullable=False, index=True)
    sku = Column(String(80), nullable=False)
    description = Column(Text)
    stock_value = Column(Numeric(15, 2), nullable=False)
    last_movement_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DebtorItem(Base):
    __tablename__ = "debtor_items"

    id = _id()
    org_id = _org()
    client_id = _client()
    period = Column(String(20), nullable=False, index=True)
    debtor_name = Column(Text, nullable=False)
    invoice_date = Column(Date, nullable=False)
    outstanding = Column(Numeric(15, 2), nullable=False)
    payment_history_score = Column(Numeric(5, 2), nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DrawingPowerStatement(Base):
    __tablename__ = "drawing_power_statements"
    __table_args__ = (
        UniqueConstraint("facility_id", "period", name="uq_dp_facility_period"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    facility_id = Column(UUID(as_uuid=True), ForeignKey("bank_facilities.id", ondelete="CASCADE"), nullable=False)
    period = Column(String(20), nullable=False)
    gross_stock = Column(Numeric(15, 2), nullable=False)
    eligible_stock = Column(Numeric(15, 2), nullable=False)
    gross_debtors = Column(Numeric(15, 2), nullable=False)
    eligible_debtors = Column(Numeric(15, 2), nullable=False)
    creditors = Column(Numeric(15, 2), nullable=False)
    drawing_power = Column(Numeric(15, 2), nullable=False)
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CertificateRecord(Base):
    __tablename__ = "certificate_records"
    __table_args__ = (
        Index("idx_certificate_records_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    cert_type = Column(String(40), nullable=False)
    title = Column(Text, nullable=False)
    fields = Column(JSONB, nullable=False, default=dict)
    validation = Column(JSONB, nullable=False, default=dict)
    status = Column(String(20), nullable=False, default="draft")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SecretarialDocument(Base):
    __tablename__ = "secretarial_documents"
    __table_args__ = (
        Index("idx_secretarial_documents_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    doc_type = Column(String(30), nullable=False)
    transcript = Column(Text)
    structured_data = Column(JSONB, nullable=False, default=dict)
    generated_text = Column(Text, nullable=False)
    generated_xml = Column(Text)
    status = Column(String(20), nullable=False, default="draft")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LeaseRecord(Base):
    __tablename__ = "lease_records"
    __table_args__ = (
        Index("idx_lease_records_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    name = Column(Text, nullable=False)
    source_text = Column(Text)
    extracted_data = Column(JSONB, nullable=False, default=dict)
    schedule = Column(JSONB, nullable=False, default=list)
    ibr_assumed = Column(Boolean, nullable=False, default=False)
    verified = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FirmCredential(Base):
    __tablename__ = "firm_credentials"
    __table_args__ = (UniqueConstraint("org_id", name="uq_firm_credentials_org"),)

    id = _id()
    org_id = _org()
    firm_name = Column(Text, nullable=False)
    icai_regn_no = Column(Text)
    founding_year = Column(Integer)
    hq_city = Column(Text)
    hq_state = Column(Text)
    partners = Column(JSONB, nullable=False, default=list)
    article_clerks = Column(Integer, nullable=False, default=0)
    total_staff = Column(Integer, nullable=False, default=0)
    gross_fee_receipts_fy1 = Column(Numeric(15, 2), nullable=False, default=0)
    gross_fee_receipts_fy2 = Column(Numeric(15, 2), nullable=False, default=0)
    gross_fee_receipts_fy3 = Column(Numeric(15, 2), nullable=False, default=0)
    industries_served = Column(JSONB, nullable=False, default=list)
    key_engagements = Column(JSONB, nullable=False, default=list)
    peer_review_status = Column(Text)
    quality_review_date = Column(Date)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class RfpBid(Base):
    __tablename__ = "rfp_bids"
    __table_args__ = (
        Index("idx_rfp_bids_org_created", "org_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    title = Column(Text, nullable=False)
    rfp_text = Column(Text, nullable=False)
    eligibility = Column(JSONB, nullable=False, default=dict)
    proposal_text = Column(Text)
    status = Column(String(20), nullable=False, default="analyzed")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UserActivityLog(Base):
    __tablename__ = "user_activity_log"
    __table_args__ = (
        Index("idx_user_activity_log_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = _client(nullable=True)
    activity_type = Column(String(40), nullable=False)
    duration_seconds = Column(Integer, nullable=False, default=0)
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TimesheetEntry(Base):
    __tablename__ = "timesheet_entries"
    __table_args__ = (
        Index("idx_timesheet_entries_org_client_date", "org_id", "client_id", "date"),
    )

    id = _id()
    org_id = _org()
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = _client()
    date = Column(Date, nullable=False, index=True)
    hours_logged = Column(Numeric(5, 2), nullable=False)
    task_description = Column(Text, nullable=False)
    billable = Column(Boolean, nullable=False, default=True)
    billing_rate = Column(Numeric(10, 2), nullable=False, default=1500)
    cost_rate = Column(Numeric(10, 2), nullable=False, default=800)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
