from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    status: Optional[str] = None


class TeamInviteCreate(BaseModel):
    email: EmailStr
    role: str


class TeamInviteAccept(BaseModel):
    token: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        if len(value) < 8:
            raise ValueError("Password must be at least 8 characters")
        return value


class UserOut(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    role: str
    status: str = "active"
    model_config = {"from_attributes": True}


class TeamInvitationOut(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: datetime
    invite_url: Optional[str] = None
    model_config = {"from_attributes": True}
