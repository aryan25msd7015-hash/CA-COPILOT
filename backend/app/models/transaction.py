import uuid
from sqlalchemy import Column, String, Text, Numeric, Date, DateTime, func, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(
            "match_status IN ('unmatched','exact','tolerance','fuzzy')",
            name="ck_transactions_match_status",
        ),
        Index("idx_transactions_org_client_created", "org_id", "client_id", "created_at"),
        Index("idx_transactions_org_client_date", "org_id", "client_id", "date"),
        Index("idx_transactions_org_match_status", "org_id", "match_status"),
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
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
    )
    invoice_no = Column(Text)
    vendor_gstin = Column(String(15), index=True)
    vendor_name = Column(Text)
    amount = Column(Numeric(15, 2))
    tax_amount = Column(Numeric(15, 2))
    date = Column(Date, index=True)
    match_status = Column(String(15), nullable=False, default="unmatched")
    match_confidence = Column(Numeric(5, 2))
    anomaly_score = Column(Numeric(5, 4))
    fraud_flag = Column(Text)
    fraud_review_status = Column(String(30), nullable=False, default="open")
    fraud_review_note = Column(Text)
    fraud_reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    fraud_reviewed_at = Column(DateTime(timezone=True))
    fraud_scanned_at = Column(DateTime(timezone=True))
    fingerprint = Column(String(64), index=True)
    source = Column(String(10), nullable=False, default="upload")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="transactions")
    document = relationship("Document", back_populates="transactions")
    anomaly_flags = relationship("AnomalyFlag", back_populates="transaction", cascade="all, delete-orphan")
