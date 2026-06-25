"""Models for the CA Exception Autopilot."""
import uuid

from sqlalchemy import (
    Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text,
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


class AutopilotSyncRun(Base):
    __tablename__ = "autopilot_sync_runs"
    __table_args__ = (
        Index("idx_autopilot_sync_org_client_started", "org_id", "client_id", "started_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    source = Column(String(30), nullable=False, default="tally_connector")
    source_name = Column(Text)
    period = Column(String(20))
    status = Column(String(20), nullable=False, default="received")
    records_received = Column(Integer, nullable=False, default=0)
    records_imported = Column(Integer, nullable=False, default=0)
    records_failed = Column(Integer, nullable=False, default=0)
    summary = Column(JSONB, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))


class AutopilotException(Base):
    __tablename__ = "autopilot_exceptions"
    __table_args__ = (
        UniqueConstraint("org_id", "fingerprint", name="uq_autopilot_exception_fingerprint"),
        Index("idx_autopilot_exceptions_org_status_updated", "org_id", "status", "updated_at"),
        Index("idx_autopilot_exceptions_org_client_status", "org_id", "client_id", "status"),
        Index("idx_autopilot_exceptions_org_source", "org_id", "source_type"),
    )

    id = _id()
    org_id = _org()
    client_id = _client()
    fingerprint = Column(String(180), nullable=False)
    source_type = Column(String(40), nullable=False)
    source_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(10), nullable=False, default="medium")
    impact_amount = Column(Numeric(15, 2), nullable=False, default=0)
    due_date = Column(Date)
    status = Column(String(20), nullable=False, default="open", index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    evidence = Column(JSONB, nullable=False, default=dict)
    recommended_actions = Column(JSONB, nullable=False, default=list)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = Column(DateTime(timezone=True))


class AutopilotReviewAction(Base):
    __tablename__ = "autopilot_review_actions"

    id = _id()
    org_id = _org()
    exception_id = Column(UUID(as_uuid=True), ForeignKey("autopilot_exceptions.id", ondelete="CASCADE"), nullable=False, index=True)
    action_type = Column(String(30), nullable=False)
    notes = Column(Text)
    payload = Column(JSONB, nullable=False, default=dict)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AutopilotFollowup(Base):
    __tablename__ = "autopilot_followups"
    __table_args__ = (
        Index("idx_autopilot_followups_org_client_created", "org_id", "client_id", "created_at"),
    )

    id = _id()
    org_id = _org()
    client_id = _client(nullable=False)
    exception_id = Column(UUID(as_uuid=True), ForeignKey("autopilot_exceptions.id", ondelete="SET NULL"), index=True)
    channel = Column(String(20), nullable=False, default="whatsapp")
    template = Column(String(60), nullable=False, default="autopilot_document_request")
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="draft")
    scheduled_at = Column(DateTime(timezone=True))
    sent_at = Column(DateTime(timezone=True))
    response_summary = Column(Text)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
