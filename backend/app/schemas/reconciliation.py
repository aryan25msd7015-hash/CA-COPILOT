import re

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
from uuid import UUID


class ReconciliationRunRequest(BaseModel):
    client_id: str
    period: str  # e.g. "Oct-2024"

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        normalized = value.strip()
        if not re.match(r"^([A-Za-z]{3}[- ][0-9]{4}|[0-9]{4}-[0-9]{2})$", normalized):
            raise ValueError("Period must use MMM-YYYY, MMM YYYY, or YYYY-MM format")
        return normalized


class ReconciliationConfigOut(BaseModel):
    client_id: UUID
    amount_tolerance: float
    date_tolerance: int
    fuzzy_threshold: int
    model_config = {"from_attributes": True}


class ReconciliationConfigUpdate(BaseModel):
    amount_tolerance: Optional[float] = Field(default=None, ge=0, le=100000)
    date_tolerance: Optional[int] = Field(default=None, ge=0, le=90)
    fuzzy_threshold: Optional[int] = Field(default=None, ge=0, le=100)


class ManualMatchRequest(BaseModel):
    purchase_transaction_id: str
    gstr2b_transaction_id: Optional[str] = None
    result_id: Optional[str] = None
    reason: str = Field(min_length=3, max_length=500)
    confidence: float = Field(default=100, ge=0, le=100)


class UnmatchRequest(BaseModel):
    purchase_transaction_id: str
    result_id: Optional[str] = None
    reason: str = Field(min_length=3, max_length=500)


class ReconciliationResultOut(BaseModel):
    id: UUID
    client_id: UUID
    period: str
    total_purchase: Optional[float] = None
    total_gstr2b: Optional[float] = None
    matched_count: Optional[int] = None
    unmatched_count: Optional[int] = None
    mismatch_value: Optional[float] = None
    status: str = "completed"
    task_id: Optional[str] = None
    error_message: Optional[str] = None
    input_summary: dict = Field(default_factory=dict)
    completed_at: Optional[datetime] = None
    run_at: datetime
    model_config = {"from_attributes": True}
