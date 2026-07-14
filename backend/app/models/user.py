import uuid
from sqlalchemy import Boolean, Column, String, Text, DateTime, func, ForeignKey, CheckConstraint, Index, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('partner','manager','article')",
            name="ck_users_role",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    email = Column(Text, unique=True, nullable=False)
    password_hash = Column(Text, nullable=False)
    role = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="active")
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    mfa_secret = Column(Text)
    mfa_recovery_hashes = Column(Text)
    mfa_confirmed_at = Column(DateTime(timezone=True))
    email_verified_at = Column(DateTime(timezone=True))
    email_verification_token_hash = Column(Text)
    email_verification_expires_at = Column(DateTime(timezone=True))
    failed_login_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True))
    password_reset_token_hash = Column(Text)
    password_reset_expires_at = Column(DateTime(timezone=True))
    last_active_at = Column(DateTime(timezone=True))
    tokens_revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization", back_populates="users")
    saved_queries = relationship("SavedQuery", back_populates="user", cascade="all, delete-orphan")


class TeamInvitation(Base):
    __tablename__ = "team_invitations"
    __table_args__ = (
        Index("idx_team_invites_org_status", "org_id", "status"),
        Index("idx_team_invites_token_hash", "token_hash", unique=True),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    email = Column(Text, nullable=False)
    role = Column(String(10), nullable=False)
    token_hash = Column(Text, nullable=False)
    invited_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status = Column(String(20), nullable=False, default="pending")
    expires_at = Column(DateTime(timezone=True), nullable=False)
    accepted_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
