import uuid
from sqlalchemy import Column, String, Text, DateTime, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID

try:
    from pgvector.sqlalchemy import Vector
    _vector_available = True
except ImportError:
    # pgvector may not be installed in all environments; fall back to Text
    Vector = None
    _vector_available = False

from app.database import Base


class LegalChunk(Base):
    __tablename__ = "legal_chunks"
    __table_args__ = (
        CheckConstraint(
            "doc_type IN ('income_tax_act','gst_act','circular','reply_template')",
            name="ck_legal_chunks_doc_type",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    doc_type = Column(String(30), nullable=False)
    content = Column(Text, nullable=False)
    # 1536-dimensional vector for text-embedding-3-small (OpenAI)
    embedding = Column(Vector(1536) if _vector_available else Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
