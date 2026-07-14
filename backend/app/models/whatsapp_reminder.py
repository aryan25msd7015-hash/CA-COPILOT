import uuid
from sqlalchemy import Column, String, DateTime, func, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from app.database import Base


class WhatsAppReminder(Base):
    __tablename__ = "whatsapp_reminders"
    __table_args__ = (
        CheckConstraint(
            "status IN ('sent','failed')",
            name="ck_wa_reminders_status",
        ),
        Index("idx_wa_reminders_org_client_sent", "org_id", "client_id", "sent_at"),
        Index("idx_wa_reminders_org_deadline", "org_id", "deadline_id"),
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
    deadline_id = Column(
        UUID(as_uuid=True),
        ForeignKey("compliance_deadlines.id"),
    )
    channel = Column(String(20), nullable=False, default="whatsapp")
    template = Column(String(50), nullable=False)
    status = Column(String(10), nullable=False, default="sent")
    provider_message_id = Column(String(100))
    provider_response = Column(JSONB, nullable=False, default=dict)
    error_message = Column(String(500))
    sent_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    deadline = relationship("ComplianceDeadline", back_populates="reminders")
