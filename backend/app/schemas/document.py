import re

from pydantic import BaseModel, field_validator
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


class UploadUrlRequest(BaseModel):
    client_id: str
    doc_type: str  # invoice|gstr2b|purchase_register|notice|trial_balance|bank_statement
    filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    mime_type: Optional[str] = None

    @field_validator("doc_type")
    @classmethod
    def normalize_doc_type(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("filename")
    @classmethod
    def safe_filename(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = value.strip()
        if len(normalized) > 180:
            raise ValueError("Filename is too long")
        if "/" in normalized or "\\" in normalized or "\x00" in normalized:
            raise ValueError("Filename must not contain path separators")
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9 ._()\\-]*$", normalized):
            raise ValueError("Filename contains unsupported characters")
        return normalized

    @field_validator("mime_type")
    @classmethod
    def normalize_mime(cls, value: Optional[str]) -> Optional[str]:
        if value is None or value == "":
            return None
        return value.strip().lower()


class UploadUrlResponse(BaseModel):
    upload_url: str
    document_id: str
    s3_key: str
    content_type: str
    expires_in_seconds: int = 300
    upload_status: str = "pending_upload"


class DocumentOut(BaseModel):
    id: UUID
    org_id: UUID
    client_id: UUID
    doc_type: str
    s3_key: str
    source: str
    status: str
    celery_task_id: Optional[str] = None
    ocr_json: Optional[Any] = None
    original_filename: Optional[str] = None
    file_size_bytes: Optional[str] = None
    mime_type: Optional[str] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    last_pipeline_error_type: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
