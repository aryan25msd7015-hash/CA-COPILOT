"""
Razorpay-related SQLAlchemy models.

Two tables live here so they can be introduced by a **single Alembic migration**
without touching existing invoice/plan tables:

    * razorpay_events          -> idempotent webhook receipts (dedupe + replay)
    * razorpay_subscriptions   -> firm-level SaaS subscriptions on CA Copilot

Note: one-time invoice payments still ride the existing invoices/payments
tables in app/models/practice_ops.py (unchanged). This module *adds* the
subscription + webhook trail — it does not replace anything.
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, JSON, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RazorpayEvent(Base):
    """One row per webhook event. Deduped by (razorpay_event_id).

    Every event is stored raw for replay/debug. `handled_at` is set once the
    event has been reduced into the invoice / subscription tables.
    """

    __tablename__ = "razorpay_events"
    __table_args__ = (
        UniqueConstraint("razorpay_event_id", name="uq_razorpay_event_id"),
    )

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=True, index=True)

    razorpay_event_id = Column(String(64), nullable=True, index=True)  # x-razorpay-event-id header
    event_type = Column(String(64), nullable=False, index=True)        # e.g. payment.captured
    signature_ok = Column(String(8), nullable=False, default="true")
    payload = Column(JSON, nullable=False)

    razorpay_order_id = Column(String(64), nullable=True, index=True)
    razorpay_payment_id = Column(String(64), nullable=True, index=True)
    razorpay_payment_link_id = Column(String(64), nullable=True, index=True)
    razorpay_subscription_id = Column(String(64), nullable=True, index=True)
    razorpay_refund_id = Column(String(64), nullable=True, index=True)

    invoice_id = Column(UUID(as_uuid=False), ForeignKey("invoices.id"), nullable=True, index=True)
    subscription_id = Column(UUID(as_uuid=False), ForeignKey("razorpay_subscriptions.id"), nullable=True, index=True)

    received_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    handled_at = Column(DateTime(timezone=True), nullable=True)
    handle_error = Column(String(500), nullable=True)


class RazorpaySubscription(Base):
    """CA firm's own subscription to CA Copilot (Starter / Pro / Enterprise)."""

    __tablename__ = "razorpay_subscriptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=False), ForeignKey("organizations.id"), nullable=False, index=True)

    razorpay_plan_id = Column(String(64), nullable=False)
    razorpay_subscription_id = Column(String(64), nullable=False, unique=True, index=True)

    plan_code = Column(String(32), nullable=False)  # 'starter' | 'pro' | 'enterprise'
    plan_period = Column(String(16), nullable=False, default="monthly")
    amount_inr = Column(Numeric(12, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="INR")

    status = Column(String(24), nullable=False, default="created", index=True)
    # created | authenticated | active | paused | halted | cancelled | completed
    current_start = Column(DateTime(timezone=True), nullable=True)
    current_end = Column(DateTime(timezone=True), nullable=True)
    next_charge_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)

    short_url = Column(String(255), nullable=True)  # Razorpay-hosted auth page

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    events = relationship("RazorpayEvent", backref="subscription", foreign_keys="RazorpayEvent.subscription_id")
