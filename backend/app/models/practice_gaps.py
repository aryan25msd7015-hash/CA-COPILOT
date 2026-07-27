"""Gap-fill practice modules: litigation, KYC/engagement, TDS, observations, etc."""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.database import Base


def _id():
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _org():
    return Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)


def _client(nullable=True):
    return Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=nullable, index=True)


def _user(nullable=True):
    return Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=nullable)


def _now():
    return Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LitigationCase(Base):
    __tablename__ = "litigation_cases"
    __table_args__ = (Index("idx_litigation_org_status", "org_id", "status"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    forum = Column(String(40), nullable=False, default="CIT(A)")  # CIT(A)|ITAT|GST|HC|SC
    case_no = Column(String(80), nullable=False)
    ay_or_period = Column(String(20))
    matter_summary = Column(Text, nullable=False)
    status = Column(String(30), nullable=False, default="open")  # open|listed|adjourned|disposed|closed
    next_hearing_date = Column(Date)
    submission_due = Column(Date)
    counsel_name = Column(Text)
    owner_user_id = _user()
    meta = Column(JSONB, nullable=False, default=dict)
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EngagementOnboarding(Base):
    __tablename__ = "engagement_onboardings"
    __table_args__ = (Index("idx_engagement_org_status", "org_id", "status"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    engagement_type = Column(String(40), nullable=False, default="statutory_audit")
    risk_category = Column(String(20), nullable=False, default="medium")  # low|medium|high
    kyc_status = Column(String(20), nullable=False, default="pending")  # pending|in_progress|complete
    aml_flags = Column(JSONB, nullable=False, default=list)
    letter_status = Column(String(20), nullable=False, default="draft")  # draft|sent|accepted|rejected
    udin = Column(String(40))
    letter_body = Column(Text)
    documents = Column(JSONB, nullable=False, default=list)
    approved_by = _user()
    approved_at = Column(DateTime(timezone=True))
    status = Column(String(20), nullable=False, default="open")
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class TdsReconRun(Base):
    __tablename__ = "tds_recon_runs"
    __table_args__ = (Index("idx_tds_recon_org_period", "org_id", "period"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    period = Column(String(20), nullable=False)  # FY / quarter
    source = Column(String(20), nullable=False, default="26AS")  # 26AS|AIS|TRACES
    status = Column(String(20), nullable=False, default="draft")  # draft|matched|exceptions|closed
    books_total = Column(Numeric(15, 2), nullable=False, default=0)
    portal_total = Column(Numeric(15, 2), nullable=False, default=0)
    matched_count = Column(Numeric(10, 0), nullable=False, default=0)
    exception_count = Column(Numeric(10, 0), nullable=False, default=0)
    exceptions = Column(JSONB, nullable=False, default=list)
    created_by = _user()
    reviewed_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class AuditObservation(Base):
    __tablename__ = "audit_observations"
    __table_args__ = (Index("idx_observations_org_status", "org_id", "status"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    engagement_ref = Column(String(80))
    area = Column(String(80), nullable=False)
    query_text = Column(Text, nullable=False)
    raised_to = Column(Text)
    status = Column(String(20), nullable=False, default="open")  # open|awaiting|responded|closed
    response_text = Column(Text)
    due_date = Column(Date)
    raised_by = _user()
    closed_by = _user()
    closed_at = Column(DateTime(timezone=True))
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class StatutoryChecklist(Base):
    __tablename__ = "statutory_checklists"
    __table_args__ = (Index("idx_checklists_org_client", "org_id", "client_id"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    framework = Column(String(40), nullable=False, default="CARO")  # CARO|CompaniesAct|IncomeTax
    entity_type = Column(String(40), nullable=False, default="pvt_ltd")
    fy = Column(String(20), nullable=False)
    items = Column(JSONB, nullable=False, default=list)
    completion_pct = Column(Numeric(5, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="in_progress")
    signed_off_by = _user()
    signed_off_at = Column(DateTime(timezone=True))
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PeerReviewPack(Base):
    __tablename__ = "peer_review_packs"
    __table_args__ = (Index("idx_peer_review_org", "org_id"),)

    id = _id()
    org_id = _org()
    cycle_label = Column(String(40), nullable=False)
    status = Column(String(20), nullable=False, default="open")
    checklist = Column(JSONB, nullable=False, default=list)
    evidence_links = Column(JSONB, nullable=False, default=list)
    readiness_score = Column(Numeric(5, 2), nullable=False, default=0)
    owner_user_id = _user()
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    __table_args__ = (Index("idx_knowledge_org_topic", "org_id", "topic"),)

    id = _id()
    org_id = _org()
    topic = Column(String(80), nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=False, default=list)
    published = Column(Boolean, nullable=False, default=True)
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class RocXbrlFiling(Base):
    __tablename__ = "roc_xbrl_filings"
    __table_args__ = (Index("idx_roc_xbrl_org_due", "org_id", "due_date"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    form_name = Column(String(40), nullable=False)  # AOC-4|MGT-7|XBRL
    fy = Column(String(20), nullable=False)
    due_date = Column(Date)
    validation_status = Column(String(30), nullable=False, default="pending")
    cost_audit_applicable = Column(Boolean, nullable=False, default=False)
    status = Column(String(20), nullable=False, default="open")
    notes = Column(Text)
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class EinvoiceValidation(Base):
    __tablename__ = "einvoice_validations"
    __table_args__ = (Index("idx_einvoice_org_client", "org_id", "client_id"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    invoice_no = Column(String(60), nullable=False)
    irn = Column(String(100))
    status = Column(String(30), nullable=False, default="pending")  # pending|valid|invalid|exempt
    turnover_threshold_hit = Column(Boolean, nullable=False, default=False)
    details = Column(JSONB, nullable=False, default=dict)
    created_by = _user()
    created_at = _now()


class ClientRiskScore(Base):
    __tablename__ = "client_risk_scores"
    __table_args__ = (
        UniqueConstraint("org_id", "client_id", name="uq_client_risk_score"),
        Index("idx_client_risk_org_score", "org_id", "score"),
    )

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    score = Column(Numeric(5, 2), nullable=False, default=0)
    tier = Column(String(10), nullable=False, default="green")  # green|amber|red
    drivers = Column(JSONB, nullable=False, default=list)
    computed_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at = _now()


class MisDashboard(Base):
    __tablename__ = "mis_dashboards"
    __table_args__ = (Index("idx_mis_org_client_period", "org_id", "client_id", "period"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    period = Column(String(20), nullable=False)
    metrics = Column(JSONB, nullable=False, default=dict)
    narrative = Column(Text)
    status = Column(String(20), nullable=False, default="draft")
    published_at = Column(DateTime(timezone=True))
    created_by = _user()
    created_at = _now()
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


class PortalAuthToken(Base):
    """Magic-link / session tokens for client portal users (separate from firm JWT)."""
    __tablename__ = "portal_auth_tokens"
    __table_args__ = (Index("idx_portal_auth_token_hash", "token_hash"),)

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    contact_id = Column(UUID(as_uuid=True), ForeignKey("client_portal_contacts.id", ondelete="CASCADE"), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True))
    created_at = _now()
