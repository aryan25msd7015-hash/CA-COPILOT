import uuid
from sqlalchemy import Column, String, Text, DateTime, func, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.database import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('invoice','gstr2b','purchase_register','notice','trial_balance','bank_statement',"
            "'udyam_certificate','inventory_ledger','debtor_ledger','balance_sheet','pnl','itr','gstr9',"
            "'lease_agreement','rfp','board_transcript')",
            name="ck_documents_doc_type",
        ),
        CheckConstraint(
            "source IN ('upload','whatsapp')",
            name="ck_documents_source",
        ),
        CheckConstraint(
            "status IN ('pending_upload','received','pending','processing','ocr_complete','ocr_failed','parse_failed','failed_validation','verified','processed')",
            name="ck_documents_status",
        ),
        Index("idx_documents_org_created", "org_id", "created_at"),
        Index("idx_documents_org_client_created", "org_id", "client_id", "created_at"),
        Index("idx_documents_org_type_status", "org_id", "doc_type", "status"),
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
    doc_type = Column(String(30), nullable=False)
    s3_key = Column(Text, nullable=False)
    ocr_text = Column(Text)
    ocr_json = Column(JSONB)
    original_filename = Column(Text)
    file_size_bytes = Column(String(30))
    mime_type = Column(String(100))
    uploaded_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    upload_expires_at = Column(DateTime(timezone=True))
    received_at = Column(DateTime(timezone=True))
    processing_started_at = Column(DateTime(timezone=True))
    processing_completed_at = Column(DateTime(timezone=True))
    last_pipeline_error_type = Column(String(60))
    source = Column(String(10), nullable=False, default="upload")
    status = Column(String(20), nullable=False, default="pending", index=True)
    celery_task_id = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    client = relationship("Client", back_populates="documents")
    transactions = relationship("Transaction", back_populates="document")


class DocumentExtraction(Base):
    __tablename__ = "document_extractions"
    __table_args__ = (
        Index("idx_document_extractions_org_client_created", "org_id", "client_id", "created_at"),
        Index("idx_document_extractions_org_supplier", "org_id", "supplier_gstin"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    supplier_name = Column(Text)
    supplier_gstin = Column(String(15))
    invoice_number = Column(Text)
    invoice_date = Column(String(30))
    taxable_value = Column(String(30))
    cgst_amount = Column(String(30))
    sgst_amount = Column(String(30))
    igst_amount = Column(String(30))
    total_amount = Column(String(30))
    confidence_score = Column(String(20))
    validation_status = Column(String(30), nullable=False, default="pending")
    validation_errors = Column(JSONB, nullable=False, default=list)
    auto_tags = Column(JSONB, nullable=False, default=list)
    raw_extracted_json = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DocumentPipelineEvent(Base):
    __tablename__ = "document_pipeline_events"
    __table_args__ = (
        Index("idx_document_pipeline_events_org_doc_created", "org_id", "document_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(40), nullable=False)
    status = Column(String(30), nullable=False)
    error_type = Column(String(60))
    diagnostic_payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
