import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (
        Index("idx_refresh_tokens_org_user", "org_id", "user_id"),
        Index("idx_refresh_tokens_hash", "token_hash", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(Text, nullable=False)
    fingerprint_hash = Column(String(64), nullable=False, default="")
    ip_address = Column(String(64))
    user_agent = Column(Text)
    risk_score = Column(String(20), nullable=False, default="low")
    risk_reasons = Column(Text)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    hard_expires_at = Column(DateTime(timezone=True))
    revoked = Column(Boolean, nullable=False, default=False)
    revoked_at = Column(DateTime(timezone=True))
    replaced_by_hash = Column(Text)
    replay_detected_at = Column(DateTime(timezone=True))
    last_used_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def is_active(self) -> bool:
        expires_at = self.expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        return not self.revoked and expires_at > datetime.now(timezone.utc)
