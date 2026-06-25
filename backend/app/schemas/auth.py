import re

from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from typing import Optional


class RegisterRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str
    org_pan: Optional[str] = None
    gstin: Optional[str] = None
    firm_type: str = "ca_firm"

    @field_validator("org_name")
    @classmethod
    def valid_org_name(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 2 or len(normalized) > 160:
            raise ValueError("Organization name must be between 2 and 160 characters")
        return normalized

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("org_pan")
    @classmethod
    def valid_pan(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{5}[0-9]{4}[A-Z]", normalized):
            raise ValueError("PAN must use the standard 10-character format")
        return normalized

    @field_validator("gstin")
    @classmethod
    def valid_gstin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if len(normalized) != 15 or not normalized.isalnum():
            raise ValueError("GSTIN must be 15 alphanumeric characters")
        return normalized

    @field_validator("firm_type")
    @classmethod
    def valid_firm_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        allowed = {"ca_firm", "solo_ca", "multi_partner_firm", "enterprise_practice"}
        if normalized not in allowed:
            raise ValueError("Invalid firm_type")
        return normalized


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_hash: Optional[str] = None
    mfa_code: Optional[str] = None
    recovery_code: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_challenge: Optional[str] = None


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_url: str
    recovery_codes: list[str]


class MfaVerifyRequest(BaseModel):
    code: str


class MfaDisableRequest(BaseModel):
    password: str
    code: Optional[str] = None
    recovery_code: Optional[str] = None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class EmailVerificationConfirmRequest(BaseModel):
    token: str


class RefreshRequest(BaseModel):
    refresh_token: str
    device_hash: Optional[str] = None


class UserOut(BaseModel):
    id: UUID
    org_id: UUID
    email: str
    role: str

    model_config = {"from_attributes": True}
