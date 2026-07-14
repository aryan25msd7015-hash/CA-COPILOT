import uuid
from sqlalchemy import Column, Integer, String, Text, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(Text, nullable=False)
    plan = Column(String(20), nullable=False, default="starter")  # starter | pro | premium
    gstin = Column(String(15))
    pan = Column(String(10))
    frn = Column(String(20))
    status = Column(String(20), nullable=False, default="active")
    firm_type = Column(String(30), nullable=False, default="ca_firm")
    registered_state = Column(String(40))
    jurisdictions = Column(JSONB, nullable=False, default=list)
    compliance_profile = Column(JSONB, nullable=False, default=dict)
    automation_policy = Column(JSONB, nullable=False, default=dict)
    data_residency_region = Column(String(40), nullable=False, default="IN")
    key_vault_ref = Column(Text)
    security_policy = Column(JSONB, nullable=False, default=dict)
    config_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    clients = relationship("Client", back_populates="organization", cascade="all, delete-orphan")
