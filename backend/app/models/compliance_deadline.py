import uuid
from sqlalchemy import Column, String, Text, Date, DateTime, func, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class ComplianceDeadline(Base):
    __tablename__ = "compliance_deadlines"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','filed','missed')",
            name="ck_deadlines_status",
        ),
        Index("idx_deadlines_org_deadline", "org_id", "deadline"),
        Index("idx_deadlines_org_client_deadline", "org_id", "client_id", "deadline"),
        Index("idx_deadlines_org_client_filing_period", "org_id", "client_id", "filing_type", "period"),
        Index("idx_deadlines_org_status_deadline", "org_id", "status", "deadline"),
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
        nullable=False,
        index=True,
    )
    # GSTR1, GSTR3B, TDS_24Q, TDS_26Q, ADVANCE_TAX, ROC
    filing_type = Column(String(20), nullable=False)
    filing_name = Column(Text, nullable=False)
    # e.g. "Oct-2024"
    period = Column(String(20), nullable=False)
    deadline = Column(Date, nullable=False, index=True)
    status = Column(String(10), nullable=False, default="pending")
    filed_at = Column(DateTime(timezone=True))
    # document type required for this filing
    doc_required = Column(String(30))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="deadlines")
    reminders = relationship("WhatsAppReminder", back_populates="deadline")
