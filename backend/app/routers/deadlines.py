from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, date, timezone
import re

from app.database import get_db
from app.models.compliance_deadline import ComplianceDeadline
from app.models.client import Client
from app.models.extensions import DeadlineClientMap
from app.engines.automation_engines import deadline_risk_score
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped

router = APIRouter()
STATUSES = {"pending", "filed", "missed"}
PERIOD_RE = re.compile(r"^([A-Za-z]{3}[- ][0-9]{4}|[0-9]{4}-[0-9]{2})$")


class DeadlineCreate(BaseModel):
    client_id: str
    filing_type: str
    filing_name: str
    period: str
    deadline: date
    doc_required: Optional[str] = None

    @field_validator("filing_type")
    @classmethod
    def valid_filing_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized or len(normalized) > 20:
            raise ValueError("Invalid filing type")
        return normalized

    @field_validator("filing_name")
    @classmethod
    def valid_filing_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Filing name cannot be blank")
        return normalized

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        normalized = value.strip()
        if not PERIOD_RE.match(normalized):
            raise ValueError("Period must use MMM-YYYY, MMM YYYY, or YYYY-MM format")
        return normalized


class DeadlineUpdate(BaseModel):
    filing_name: Optional[str] = None
    deadline: Optional[date] = None
    status: Optional[str] = None
    filed_at: Optional[datetime] = None
    doc_required: Optional[str] = None

    @field_validator("filing_name")
    @classmethod
    def valid_filing_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("Filing name cannot be blank")
        return normalized

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        normalized = value.strip().lower()
        if normalized not in STATUSES:
            raise ValueError("Invalid deadline status")
        return normalized


def _client_or_404(db: Session, org_id, client_id: str) -> Client:
    client = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    return client


def _risk_tier(score: float) -> str:
    if score >= 7:
        return "high"
    if score >= 4:
        return "medium"
    return "low"


def _risk_map(db: Session, org_id, deadlines: list[ComplianceDeadline]) -> dict[tuple[str, str, str], DeadlineClientMap]:
    if not deadlines:
        return {}
    client_ids = {d.client_id for d in deadlines}
    filing_types = {d.filing_type for d in deadlines}
    periods = {d.period for d in deadlines}
    rows = (
        scoped(db, DeadlineClientMap, org_id)
        .filter(
            DeadlineClientMap.client_id.in_(client_ids),
            DeadlineClientMap.filing_type.in_(filing_types),
            DeadlineClientMap.period.in_(periods),
        )
        .all()
    )
    return {(str(row.client_id), row.filing_type, row.period): row for row in rows}


@router.get("")
def list_deadlines(request: Request, db: Session = Depends(get_db),
                   client_id: Optional[str] = None, status: Optional[str] = None,
                   due_from: Optional[date] = None, due_to: Optional[date] = None,
                   skip: int = 0, limit: int = 2000,
                   _=Depends(get_current_user)):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    query = scoped(db, ComplianceDeadline, request.state.org_id)
    if client_id:
        _client_or_404(db, request.state.org_id, client_id)
        query = query.filter(ComplianceDeadline.client_id == client_id)
    if status:
        normalized_status = status.strip().lower()
        if normalized_status not in STATUSES:
            raise HTTPException(422, "Invalid deadline status")
        query = query.filter(ComplianceDeadline.status == normalized_status)
    if due_from:
        query = query.filter(ComplianceDeadline.deadline >= due_from)
    if due_to:
        query = query.filter(ComplianceDeadline.deadline <= due_to)
    deadlines = query.order_by(ComplianceDeadline.deadline.asc()).offset(skip).limit(limit).all()
    risks = _risk_map(db, request.state.org_id, deadlines)
    return [_dl_out(d, risks.get((str(d.client_id), d.filing_type, d.period))) for d in deadlines]


@router.post("", status_code=201)
def create_deadline(req: DeadlineCreate, request: Request,
                    db: Session = Depends(get_db), _=Depends(get_current_user)):
    client = _client_or_404(db, request.state.org_id, req.client_id)
    existing = scoped(db, ComplianceDeadline, request.state.org_id).filter(
        ComplianceDeadline.client_id == req.client_id,
        ComplianceDeadline.filing_type == req.filing_type,
        ComplianceDeadline.period == req.period,
    ).first()
    if existing:
        raise HTTPException(409, "Deadline already exists for this client, filing type, and period")
    dl = ComplianceDeadline(org_id=request.state.org_id, **req.model_dump())
    db.add(dl)
    calendar_row = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.client_id == req.client_id,
        DeadlineClientMap.filing_type == req.filing_type,
        DeadlineClientMap.period == req.period,
    ).first()
    if not calendar_row:
        calendar_row = DeadlineClientMap(
            org_id=request.state.org_id,
            client_id=req.client_id,
            filing_type=req.filing_type,
            filing_name=req.filing_name,
            period=req.period,
            deadline=req.deadline,
        )
        db.add(calendar_row)
    else:
        calendar_row.filing_name = req.filing_name
        calendar_row.deadline = req.deadline
    calendar_row.risk_score = deadline_risk_score(
        req.deadline, bool(calendar_row.data_received),
        calendar_row.late_count_last_12m or 0,
        bool(calendar_row.has_open_notice), client.health_score,
    )
    db.commit()
    db.refresh(dl)
    return _dl_out(dl, calendar_row)


@router.patch("/{deadline_id}")
def update_deadline(deadline_id: str, req: DeadlineUpdate,
                    request: Request, db: Session = Depends(get_db),
                    _=Depends(get_current_user)):
    dl = (scoped(db, ComplianceDeadline, request.state.org_id)
          .filter(ComplianceDeadline.id == deadline_id).first())
    if not dl:
        raise HTTPException(404, "Deadline not found")
    updates = req.model_dump(exclude_unset=True)
    if not updates:
        return _dl_out(dl)
    if req.filing_name is not None:
        dl.filing_name = req.filing_name
    if req.deadline is not None:
        dl.deadline = req.deadline
    if req.doc_required is not None:
        dl.doc_required = req.doc_required
    if req.status:
        dl.status = req.status
        if req.status == "filed" and not req.filed_at:
            dl.filed_at = datetime.now(timezone.utc)
        elif req.status != "filed":
            dl.filed_at = None
    if req.filed_at:
        dl.filed_at = req.filed_at
    calendar_row = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.client_id == dl.client_id,
        DeadlineClientMap.filing_type == dl.filing_type,
        DeadlineClientMap.period == dl.period,
    ).first()
    if calendar_row:
        if req.filing_name is not None:
            calendar_row.filing_name = req.filing_name
        if req.deadline is not None:
            calendar_row.deadline = req.deadline
        client = _client_or_404(db, request.state.org_id, str(dl.client_id))
        calendar_row.risk_score = deadline_risk_score(
            calendar_row.deadline, bool(calendar_row.data_received),
            calendar_row.late_count_last_12m or 0,
            bool(calendar_row.has_open_notice), client.health_score,
        )
        if req.status:
            calendar_row.status = req.status
            calendar_row.filed_at = dl.filed_at
        if req.filed_at:
            calendar_row.filed_at = req.filed_at
    db.commit()
    return _dl_out(dl, calendar_row)


@router.get("/client/{client_id}")
def client_deadlines(client_id: str, request: Request,
                     db: Session = Depends(get_db), status: Optional[str] = None,
                     due_from: Optional[date] = None, due_to: Optional[date] = None,
                     skip: int = 0, limit: int = 2000,
                     _=Depends(get_current_user)):
    _client_or_404(db, request.state.org_id, client_id)
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    query = scoped(db, ComplianceDeadline, request.state.org_id).filter(ComplianceDeadline.client_id == client_id)
    if status:
        normalized_status = status.strip().lower()
        if normalized_status not in STATUSES:
            raise HTTPException(422, "Invalid deadline status")
        query = query.filter(ComplianceDeadline.status == normalized_status)
    if due_from:
        query = query.filter(ComplianceDeadline.deadline >= due_from)
    if due_to:
        query = query.filter(ComplianceDeadline.deadline <= due_to)
    deadlines = query.order_by(ComplianceDeadline.deadline.asc()).offset(skip).limit(limit).all()
    risks = _risk_map(db, request.state.org_id, deadlines)
    return [_dl_out(d, risks.get((str(d.client_id), d.filing_type, d.period))) for d in deadlines]


def _dl_out(d: ComplianceDeadline, risk_row: DeadlineClientMap | None = None) -> dict:
    risk_score = float(risk_row.risk_score or 0) if risk_row else 0.0
    days_until_due = (d.deadline - date.today()).days
    return {
        "id": str(d.id), "client_id": str(d.client_id),
        "filing_type": d.filing_type, "filing_name": d.filing_name,
        "period": d.period, "deadline": str(d.deadline),
        "status": d.status, "filed_at": d.filed_at.isoformat() if d.filed_at else None,
        "doc_required": d.doc_required,
        "risk_score": risk_score,
        "risk_tier": _risk_tier(risk_score),
        "calendar_item_id": str(risk_row.id) if risk_row else None,
        "days_until_due": days_until_due,
        "data_received": bool(risk_row.data_received) if risk_row else False,
        "late_count_last_12m": risk_row.late_count_last_12m if risk_row else 0,
        "has_open_notice": bool(risk_row.has_open_notice) if risk_row else False,
    }
