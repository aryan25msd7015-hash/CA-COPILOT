"""System-level tenant provisioning and immutable audit records."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.database import Base


class SystemAuditLog(Base):
    __tablename__ = "system_audit_logs"
    __table_args__ = (
        Index("idx_system_audit_org_created", "org_id", "created_at"),
        Index("idx_system_audit_actor_created", "actor_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action = Column(String(80), nullable=False)
    ip_address = Column(String(64))
    user_agent = Column(Text)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OrganizationAgentState(Base):
    __tablename__ = "organization_agent_states"
    __table_args__ = (
        Index("idx_agent_state_org_status", "org_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = Column(String(30), nullable=False, default="ready")
    vector_namespace = Column(Text, nullable=False)
    enabled_agents = Column(JSONB, nullable=False, default=list)
    readiness_checks = Column(JSONB, nullable=False, default=dict)
    last_event = Column(String(80), nullable=False, default="organization.initialized")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SystemEvent(Base):
    __tablename__ = "system_events"
    __table_args__ = (
        Index("idx_system_events_org_created", "org_id", "created_at"),
        Index("idx_system_events_org_status", "org_id", "status", "created_at"),
        Index("idx_system_events_org_type", "org_id", "event_type", "created_at"),
        Index("idx_system_events_aggregate", "org_id", "aggregate_type", "aggregate_id"),
        Index("idx_system_events_correlation", "correlation_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    event_type = Column(String(120), nullable=False)
    aggregate_type = Column(String(60), nullable=False)
    aggregate_id = Column(String(80), nullable=False)
    source_module = Column(String(60), nullable=False)
    status = Column(String(30), nullable=False, default="recorded")
    correlation_id = Column(String(80), nullable=False)
    causation_id = Column(String(80))
    payload = Column(JSONB, nullable=False, default=dict)
    dispatch_attempts = Column(Integer, nullable=False, default=0)
    last_error = Column(Text)
    dispatched_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
