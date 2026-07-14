import uuid
from sqlalchemy import Column, String, Text, Numeric, Boolean, DateTime, func, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class AnomalyFlag(Base):
    __tablename__ = "anomaly_flags"
    __table_args__ = (
        Index("idx_anomaly_flags_org_review_risk", "org_id", "reviewed", "risk_score"),
        Index("idx_anomaly_flags_org_client_risk", "org_id", "client_id", "risk_score"),
        Index("idx_anomaly_flags_org_type", "org_id", "flag_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_id = Column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
    )
    # benford | round_number | weekend | duplicate | threshold_gaming | vendor_spike | isolation_forest
    flag_type = Column(String(30), nullable=False)
    risk_score = Column(Numeric(5, 4))
    details = Column(JSONB)
    reviewed = Column(Boolean, nullable=False, default=False)
    review_status = Column(String(30), nullable=False, default="open")
    review_note = Column(Text)
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    reviewed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="anomaly_flags")
    transaction = relationship("Transaction", back_populates="anomaly_flags")
