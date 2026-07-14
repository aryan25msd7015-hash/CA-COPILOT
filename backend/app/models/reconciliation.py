import uuid
from sqlalchemy import CheckConstraint, Column, Numeric, Integer, DateTime, func, Text, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class ReconciliationConfig(Base):
    __tablename__ = "reconciliation_config"

    # client_id is also the primary key — one config row per client
    client_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clients.id", ondelete="CASCADE"),
        primary_key=True,
    )
    amount_tolerance = Column(Numeric(10, 2), nullable=False, default=5)
    date_tolerance = Column(Integer, nullable=False, default=3)
    fuzzy_threshold = Column(Integer, nullable=False, default=85)

    client = relationship("Client", back_populates="reconciliation_config")


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"
    __table_args__ = (
        Index("idx_reconciliation_results_org_client_run", "org_id", "client_id", "run_at"),
        Index("idx_reconciliation_results_org_client_status", "org_id", "client_id", "status"),
        CheckConstraint("status IN ('queued','running','completed','failed')", name="ck_reconciliation_results_status"),
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
    period = Column(Text, nullable=False)
    total_purchase = Column(Numeric(15, 2))
    total_gstr2b = Column(Numeric(15, 2))
    matched_count = Column(Integer)
    unmatched_count = Column(Integer)
    mismatch_value = Column(Numeric(15, 2))
    status = Column(String(20), nullable=False, default="completed")
    task_id = Column(String(50))
    error_message = Column(Text)
    input_summary = Column(JSONB, nullable=False, default=dict)
    completed_at = Column(DateTime(timezone=True))
    run_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReconciliationMatchAction(Base):
    __tablename__ = "reconciliation_match_actions"
    __table_args__ = (
        Index("idx_recon_actions_org_client_created", "org_id", "client_id", "created_at"),
        Index("idx_recon_actions_purchase", "org_id", "purchase_transaction_id", "created_at"),
        CheckConstraint("action_type IN ('manual_match','unmatch','rollback')", name="ck_recon_actions_type"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    result_id = Column(UUID(as_uuid=True), ForeignKey("reconciliation_results.id", ondelete="SET NULL"), index=True)
    purchase_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="CASCADE"), nullable=False, index=True)
    gstr2b_transaction_id = Column(UUID(as_uuid=True), ForeignKey("transactions.id", ondelete="SET NULL"), index=True)
    action_type = Column(String(30), nullable=False)
    previous_status = Column(String(15))
    previous_confidence = Column(Numeric(5, 2))
    new_status = Column(String(15), nullable=False)
    new_confidence = Column(Numeric(5, 2))
    reason = Column(Text)
    evidence = Column(JSONB, nullable=False, default=dict)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
