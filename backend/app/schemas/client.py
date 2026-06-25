import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


ENTITY_TYPES = {"pvt_ltd", "llp", "partnership", "proprietorship", "trust"}
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
TAN_RE = re.compile(r"^[A-Z]{4}[0-9]{5}[A-Z]$")


class ClientBase(BaseModel):
    name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    email: Optional[EmailStr] = None
    whatsapp_number: Optional[str] = None
    industry: Optional[str] = None
    entity_type: Optional[str] = None
    cin: Optional[str] = None
    registered_office: Optional[str] = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Client name cannot be blank")
        return normalized

    @field_validator("gstin")
    @classmethod
    def valid_gstin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if not GSTIN_RE.match(normalized):
            raise ValueError("GSTIN is invalid")
        return normalized

    @field_validator("pan")
    @classmethod
    def valid_pan(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if not PAN_RE.match(normalized):
            raise ValueError("PAN is invalid")
        return normalized

    @field_validator("tan")
    @classmethod
    def valid_tan(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip().upper()
        if not TAN_RE.match(normalized):
            raise ValueError("TAN is invalid")
        return normalized

    @field_validator("whatsapp_number")
    @classmethod
    def valid_whatsapp(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = re.sub(r"[\s\-()]", "", value.strip())
        if not re.fullmatch(r"\+?[1-9][0-9]{9,14}", normalized):
            raise ValueError("WhatsApp number must be 10 to 15 digits with optional + prefix")
        return normalized

    @field_validator("entity_type")
    @classmethod
    def valid_entity_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in ENTITY_TYPES:
            raise ValueError("Invalid entity type")
        return normalized

    @field_validator("cin")
    @classmethod
    def normalize_cin(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return value.strip().upper()


class ClientCreate(ClientBase):
    name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    email: Optional[EmailStr] = None
    whatsapp_number: Optional[str] = None
    industry: Optional[str] = None
    entity_type: str = "pvt_ltd"
    cin: Optional[str] = None
    registered_office: Optional[str] = None


class ClientUpdate(ClientBase):
    name: Optional[str] = None
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    email: Optional[EmailStr] = None
    whatsapp_number: Optional[str] = None
    industry: Optional[str] = None
    entity_type: Optional[str] = None
    cin: Optional[str] = None
    registered_office: Optional[str] = None


class ClientOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    email: Optional[str] = None
    whatsapp_number: Optional[str] = None
    whatsapp_consent_at: Optional[datetime] = None
    health_score: int
    industry: Optional[str] = None
    entity_type: str = "pvt_ltd"
    cin: Optional[str] = None
    registered_office: Optional[str] = None
    benchmark_consent_at: Optional[datetime] = None
    status: str = "active"
    client_partition: Optional[str] = None
    lifecycle_metadata: dict = {}
    deleted_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ClientListOut(BaseModel):
    id: UUID
    org_id: UUID
    name: str
    gstin: Optional[str] = None
    pan: Optional[str] = None
    tan: Optional[str] = None
    email: Optional[str] = None
    health_score: int
    industry: Optional[str] = None
    entity_type: str = "pvt_ltd"
    cin: Optional[str] = None
    registered_office: Optional[str] = None
    whatsapp_number: Optional[str] = None
    whatsapp_consent_at: Optional[datetime] = None
    benchmark_consent_at: Optional[datetime] = None
    status: str = "active"
    client_partition: Optional[str] = None

    model_config = {"from_attributes": True}
