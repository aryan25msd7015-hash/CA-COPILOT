"""ORM models for Hybrid Audit Engine artifacts and evaluation runs."""
import uuid
from sqlalchemy import Column, String, Text, Numeric, Boolean, DateTime, Integer, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.database import Base


class AuditModelArtifact(Base):
    __tablename__ = "audit_model_artifacts"
    __table_args__ = (
        Index("idx_audit_model_artifacts_org_name", "org_id", "name"),
        Index("idx_audit_model_artifacts_org_active", "org_id", "is_active"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name = Column(String(80), nullable=False)
    version = Column(String(40), nullable=False, default="latest")
    backend = Column(String(30), nullable=False, default="sklearn")
    local_path = Column(Text)
    s3_key = Column(Text)
    metrics = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditEngineRun(Base):
    __tablename__ = "audit_engine_runs"
    __table_args__ = (
        Index("idx_audit_engine_runs_org_created", "org_id", "created_at"),
        Index("idx_audit_engine_runs_org_client", "org_id", "client_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_type = Column(String(40), nullable=False, default="score")  # train|score|eval|sample
    status = Column(String(20), nullable=False, default="completed")
    summary = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditBanditEvent(Base):
    __tablename__ = "audit_bandit_events"
    __table_args__ = (
        Index("idx_audit_bandit_events_org_created", "org_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    candidate_id = Column(String(80))
    arm = Column(Integer, nullable=False, default=1)
    reward = Column(Numeric(6, 4))
    review_status = Column(String(30))
    context = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
