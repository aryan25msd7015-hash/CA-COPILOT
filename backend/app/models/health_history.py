import uuid
from sqlalchemy import Column, Integer, String, DateTime, func, ForeignKey, CheckConstraint, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class ClientHealthHistory(Base):
    __tablename__ = "client_health_history"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('green','amber','red')",
            name="ck_health_history_tier",
        ),
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
    score = Column(Integer, nullable=False)
    tier = Column(String(10), nullable=False)
    components = Column(JSONB)
    computed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="health_history")


class ClientHealthScoreEvent(Base):
    __tablename__ = "client_health_score_events"
    __table_args__ = (
        Index("idx_health_events_org_client_created", "org_id", "client_id", "created_at"),
        Index("idx_health_events_org_severity", "org_id", "severity"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = Column(String(40), nullable=False)
    severity = Column(String(20), nullable=False, default="info")
    previous_score = Column(Integer)
    current_score = Column(Integer, nullable=False)
    delta = Column(Integer, nullable=False, default=0)
    reason_manifest = Column(JSONB, nullable=False, default=dict)
    explanation = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
