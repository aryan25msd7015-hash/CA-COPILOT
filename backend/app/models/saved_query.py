import uuid
from sqlalchemy import Column, Text, DateTime, func, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class SavedQuery(Base):
    __tablename__ = "saved_queries"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", "name", name="uq_saved_queries_user_name"),
        Index("idx_saved_queries_org_user_created", "org_id", "user_id", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(Text, nullable=False)
    nl_query = Column(Text, nullable=False)
    run_count = Column(Integer, nullable=False, default=0)
    last_run_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="saved_queries")
