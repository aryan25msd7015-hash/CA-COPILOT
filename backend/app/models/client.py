import uuid
from sqlalchemy import CheckConstraint, Column, String, Text, Integer, DateTime, func, ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint("health_score >= 0 AND health_score <= 100", name="ck_clients_health_score"),
        CheckConstraint(
            "entity_type IN ('pvt_ltd','llp','partnership','proprietorship','trust')",
            name="ck_clients_entity_type",
        ),
        Index("idx_clients_org_health_name", "org_id", "health_score", "name"),
        Index("idx_clients_org_gstin_unique", "org_id", "gstin", unique=True, postgresql_where=text("gstin IS NOT NULL")),
        Index("idx_clients_org_pan_unique", "org_id", "pan", unique=True, postgresql_where=text("pan IS NOT NULL")),
        Index("idx_clients_org_status", "org_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    gstin = Column(String(15))
    pan = Column(String(10))
    tan = Column(String(10))
    email = Column(Text)
    whatsapp_number = Column(String(20))
    whatsapp_consent_at = Column(DateTime(timezone=True))
    health_score = Column(Integer, nullable=False, default=100)
    industry = Column(String(50))
    entity_type = Column(String(30), nullable=False, default="pvt_ltd")
    cin = Column(String(30))
    registered_office = Column(Text)
    benchmark_consent_at = Column(DateTime(timezone=True))
    benchmark_consent_source = Column(String(30))
    benchmark_consent_note = Column(Text)
    benchmark_consent_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status = Column(String(20), nullable=False, default="active")
    client_partition = Column(Text)
    lifecycle_metadata = Column(JSONB, nullable=False, default=dict)
    deleted_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="clients")
    documents = relationship("Document", back_populates="client", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="client", cascade="all, delete-orphan")
    deadlines = relationship("ComplianceDeadline", back_populates="client", cascade="all, delete-orphan")
    health_history = relationship("ClientHealthHistory", back_populates="client", cascade="all, delete-orphan")
    anomaly_flags = relationship("AnomalyFlag", back_populates="client", cascade="all, delete-orphan")
    reconciliation_config = relationship(
        "ReconciliationConfig",
        back_populates="client",
        uselist=False,
        cascade="all, delete-orphan",
    )
