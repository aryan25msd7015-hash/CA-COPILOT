"""
Email delivery event model — one row per Resend webhook event, plus a
`sends_log` for outbound message audit.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EmailEvent(Base):
    """Deduped by (resend_event_id) — idempotent webhook replay-safe."""

    __tablename__ = "email_events"
    __table_args__ = (
        UniqueConstraint("resend_event_id", name="uq_email_event_id"),
        Index("ix_email_event_recipient", "recipient"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True, index=True)

    resend_event_id = Column(String(64), nullable=True, index=True)   # svix-id
    resend_message_id = Column(String(64), nullable=True, index=True) # data.email_id
    event_type = Column(String(48), nullable=False, index=True)       # email.sent / delivered / bounced / opened / clicked / complained / delivery_delayed
    recipient = Column(String(255), nullable=True)
    template = Column(String(64), nullable=True)
    tags = Column(JSON, nullable=True)
    payload = Column(JSON, nullable=False)

    signature_ok = Column(String(8), nullable=False, default="true")
    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    handled_at = Column(DateTime(timezone=True), nullable=True)
    handle_error = Column(String(500), nullable=True)


class EmailSendLog(Base):
    """Row per outbound send attempt (before we know delivery outcome)."""

    __tablename__ = "email_sends"
    __table_args__ = (
        Index("ix_email_sends_org_template", "org_id", "template"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True, index=True)

    resend_message_id = Column(String(64), nullable=True, index=True)
    idempotency_key = Column(String(80), nullable=True, index=True)
    template = Column(String(64), nullable=False)
    recipient = Column(String(255), nullable=False)
    subject = Column(String(255), nullable=False)
    status = Column(String(24), nullable=False, default="queued")
    # queued | sent | delivered | bounced | complained | failed | dry_run
    dry_run = Column(String(8), nullable=False, default="false")
    error = Column(String(500), nullable=True)
    tags = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)
