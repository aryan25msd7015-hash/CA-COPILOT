"""APIs for priority gap modules slotted into the four-tier RBAC matrix."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anomaly_flag import AnomalyFlag
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.practice_gaps import (
    AuditObservation, ClientRiskScore, EinvoiceValidation, EngagementOnboarding,
    KnowledgeArticle, LitigationCase, MisDashboard, PeerReviewPack,
    RocXbrlFiling, StatutoryChecklist, TdsReconRun,
)
from app.models.practice_ops import PracticeInvoice
from app.models.user import User
from app.utils.deps import get_current_user, require_action, require_feature
from app.utils.scoped_query import scoped

router = APIRouter()


def _page(skip: int, limit: int, max_limit: int = 500):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > max_limit:
        raise HTTPException(422, f"limit must be between 1 and {max_limit}")
    return skip, limit


def _dt(value):
    return value.isoformat() if value else None


def _d(value):
    return value.isoformat() if value else None


def _num(value):
    return float(value or 0)


def _client(db: Session, org_id, client_id: str):
    row = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not row:
        raise HTTPException(404, "Client not found")
    return row


def _client_names(db: Session, org_id):
    return {str(row.id): row.name for row in scoped(db, Client, org_id).all()}


# ── Litigation Tracker ──────────────────────────────────────────────────────

class LitigationIn(BaseModel):
    client_id: str
    forum: str = "CIT(A)"
    case_no: str = Field(min_length=1, max_length=80)
    ay_or_period: Optional[str] = None
    matter_summary: str = Field(min_length=1)
    status: str = "open"
    next_hearing_date: Optional[date] = None
    submission_due: Optional[date] = None
    counsel_name: Optional[str] = None
    owner_user_id: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)


class LitigationPatch(BaseModel):
    status: Optional[str] = None
    next_hearing_date: Optional[date] = None
    submission_due: Optional[date] = None
    matter_summary: Optional[str] = None
    counsel_name: Optional[str] = None
    owner_user_id: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


def _litigation_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "forum": row.forum,
        "case_no": row.case_no,
        "ay_or_period": row.ay_or_period,
        "matter_summary": row.matter_summary,
        "status": row.status,
        "next_hearing_date": _d(row.next_hearing_date),
        "submission_due": _d(row.submission_due),
        "counsel_name": row.counsel_name,
        "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        "meta": row.meta or {},
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/litigation")
def list_litigation(
    request: Request,
    client_id: str = "",
    status: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("litigation_tracker")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, LitigationCase, request.state.org_id)
    if client_id:
        q = q.filter(LitigationCase.client_id == client_id)
    if status:
        q = q.filter(LitigationCase.status == status)
    clients = _client_names(db, request.state.org_id)
    rows = q.order_by(LitigationCase.next_hearing_date.asc().nullslast()).offset(skip).limit(limit).all()
    return [_litigation_out(r, clients) for r in rows]


@router.post("/litigation", status_code=201)
def create_litigation(
    payload: LitigationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("litigation_tracker")),
):
    _client(db, request.state.org_id, payload.client_id)
    row = LitigationCase(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _litigation_out(row, _client_names(db, request.state.org_id))


@router.patch("/litigation/{case_id}")
def patch_litigation(
    case_id: str,
    payload: LitigationPatch,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("litigation_tracker")),
):
    row = scoped(db, LitigationCase, request.state.org_id).filter(LitigationCase.id == case_id).first()
    if not row:
        raise HTTPException(404, "Litigation case not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("status") in {"closed", "disposed"}:
        from app.utils.permissions import can_perform
        if not can_perform(user.role, "litigation:close"):
            raise HTTPException(403, "Only CA (Manager)+ can close litigation")
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _litigation_out(row, _client_names(db, request.state.org_id))


# ── Engagement & KYC/AML ────────────────────────────────────────────────────

class EngagementIn(BaseModel):
    client_id: str
    engagement_type: str = "statutory_audit"
    risk_category: str = "medium"
    kyc_status: str = "pending"
    aml_flags: list[Any] = Field(default_factory=list)
    letter_status: str = "draft"
    udin: Optional[str] = None
    letter_body: Optional[str] = None
    documents: list[Any] = Field(default_factory=list)


class EngagementPatch(BaseModel):
    risk_category: Optional[str] = None
    kyc_status: Optional[str] = None
    aml_flags: Optional[list[Any]] = None
    letter_status: Optional[str] = None
    udin: Optional[str] = None
    letter_body: Optional[str] = None
    documents: Optional[list[Any]] = None
    status: Optional[str] = None
    approve: bool = False


def _engagement_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "engagement_type": row.engagement_type,
        "risk_category": row.risk_category,
        "kyc_status": row.kyc_status,
        "aml_flags": row.aml_flags or [],
        "letter_status": row.letter_status,
        "udin": row.udin,
        "letter_body": row.letter_body,
        "documents": row.documents or [],
        "status": row.status,
        "approved_by": str(row.approved_by) if row.approved_by else None,
        "approved_at": _dt(row.approved_at),
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/engagement")
def list_engagements(
    request: Request,
    client_id: str = "",
    status: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("engagement_kyc")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, EngagementOnboarding, request.state.org_id)
    if client_id:
        q = q.filter(EngagementOnboarding.client_id == client_id)
    if status:
        q = q.filter(EngagementOnboarding.status == status)
    clients = _client_names(db, request.state.org_id)
    return [_engagement_out(r, clients) for r in q.order_by(EngagementOnboarding.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/engagement", status_code=201)
def create_engagement(
    payload: EngagementIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("engagement_kyc")),
):
    _client(db, request.state.org_id, payload.client_id)
    row = EngagementOnboarding(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _engagement_out(row, _client_names(db, request.state.org_id))


@router.patch("/engagement/{engagement_id}")
def patch_engagement(
    engagement_id: str,
    payload: EngagementPatch,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("engagement_kyc")),
):
    row = scoped(db, EngagementOnboarding, request.state.org_id).filter(EngagementOnboarding.id == engagement_id).first()
    if not row:
        raise HTTPException(404, "Engagement not found")
    values = payload.model_dump(exclude_unset=True)
    approve = values.pop("approve", False)
    if approve:
        from app.utils.permissions import can_perform
        if not can_perform(user.role, "engagement:approve"):
            raise HTTPException(403, "Only CA (Manager)+ can approve engagement letters")
        row.approved_by = user.id
        row.approved_at = datetime.now(timezone.utc)
        row.letter_status = "accepted"
        row.status = "active"
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _engagement_out(row, _client_names(db, request.state.org_id))


# ── TDS/TCS Reconciliation ──────────────────────────────────────────────────

class TdsReconIn(BaseModel):
    client_id: str
    period: str
    source: str = "26AS"
    books_total: float = 0
    portal_total: float = 0
    matched_count: int = 0
    exception_count: int = 0
    exceptions: list[Any] = Field(default_factory=list)
    status: str = "draft"


class TdsReconPatch(BaseModel):
    status: Optional[str] = None
    books_total: Optional[float] = None
    portal_total: Optional[float] = None
    matched_count: Optional[int] = None
    exception_count: Optional[int] = None
    exceptions: Optional[list[Any]] = None
    mark_reviewed: bool = False


def _tds_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "period": row.period,
        "source": row.source,
        "status": row.status,
        "books_total": _num(row.books_total),
        "portal_total": _num(row.portal_total),
        "variance": round(_num(row.books_total) - _num(row.portal_total), 2),
        "matched_count": int(row.matched_count or 0),
        "exception_count": int(row.exception_count or 0),
        "exceptions": row.exceptions or [],
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/tds-recon")
def list_tds_recon(
    request: Request,
    client_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("tds_tcs_reconciliation")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, TdsReconRun, request.state.org_id)
    if client_id:
        q = q.filter(TdsReconRun.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    return [_tds_out(r, clients) for r in q.order_by(TdsReconRun.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/tds-recon", status_code=201)
def create_tds_recon(
    payload: TdsReconIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("tds_tcs_reconciliation")),
):
    _client(db, request.state.org_id, payload.client_id)
    data = payload.model_dump()
    row = TdsReconRun(org_id=request.state.org_id, created_by=user.id, **data)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _tds_out(row, _client_names(db, request.state.org_id))


@router.patch("/tds-recon/{run_id}")
def patch_tds_recon(
    run_id: str,
    payload: TdsReconPatch,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("tds_tcs_reconciliation")),
):
    row = scoped(db, TdsReconRun, request.state.org_id).filter(TdsReconRun.id == run_id).first()
    if not row:
        raise HTTPException(404, "TDS recon run not found")
    values = payload.model_dump(exclude_unset=True)
    mark_reviewed = values.pop("mark_reviewed", False)
    if mark_reviewed:
        from app.utils.permissions import can_perform
        if not can_perform(user.role, "reconciliation:approve"):
            raise HTTPException(403, "Only CA (Manager)+ can approve TDS recon")
        row.reviewed_by = user.id
        row.status = values.get("status") or "closed"
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _tds_out(row, _client_names(db, request.state.org_id))


# ── Query & Observation Ledger ──────────────────────────────────────────────

class ObservationIn(BaseModel):
    client_id: str
    engagement_ref: Optional[str] = None
    area: str
    query_text: str
    raised_to: Optional[str] = None
    due_date: Optional[date] = None


class ObservationPatch(BaseModel):
    status: Optional[str] = None
    response_text: Optional[str] = None
    due_date: Optional[date] = None
    close: bool = False


def _obs_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "engagement_ref": row.engagement_ref,
        "area": row.area,
        "query_text": row.query_text,
        "raised_to": row.raised_to,
        "status": row.status,
        "response_text": row.response_text,
        "due_date": _d(row.due_date),
        "raised_by": str(row.raised_by) if row.raised_by else None,
        "closed_by": str(row.closed_by) if row.closed_by else None,
        "closed_at": _dt(row.closed_at),
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/observations")
def list_observations(
    request: Request,
    client_id: str = "",
    status: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("query_observation_ledger")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, AuditObservation, request.state.org_id)
    if client_id:
        q = q.filter(AuditObservation.client_id == client_id)
    if status:
        q = q.filter(AuditObservation.status == status)
    clients = _client_names(db, request.state.org_id)
    return [_obs_out(r, clients) for r in q.order_by(AuditObservation.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/observations", status_code=201)
def create_observation(
    payload: ObservationIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("query_observation_ledger")),
):
    _client(db, request.state.org_id, payload.client_id)
    row = AuditObservation(org_id=request.state.org_id, raised_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _obs_out(row, _client_names(db, request.state.org_id))


@router.patch("/observations/{obs_id}")
def patch_observation(
    obs_id: str,
    payload: ObservationPatch,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("query_observation_ledger")),
):
    row = scoped(db, AuditObservation, request.state.org_id).filter(AuditObservation.id == obs_id).first()
    if not row:
        raise HTTPException(404, "Observation not found")
    values = payload.model_dump(exclude_unset=True)
    close = values.pop("close", False)
    if close:
        from app.utils.permissions import can_perform
        if not can_perform(user.role, "observation:close"):
            raise HTTPException(403, "Only CA (Manager)+ can close observations")
        row.closed_by = user.id
        row.closed_at = datetime.now(timezone.utc)
        row.status = "closed"
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _obs_out(row, _client_names(db, request.state.org_id))


# ── Statutory Checklist Engine ──────────────────────────────────────────────

CARO_TEMPLATE = [
    {"code": "3(i)(a)", "title": "PPE physical verification", "status": "pending", "notes": ""},
    {"code": "3(i)(b)", "title": "Title deeds of immovable properties", "status": "pending", "notes": ""},
    {"code": "3(ii)", "title": "Inventory verification", "status": "pending", "notes": ""},
    {"code": "3(iii)", "title": "Loans / advances / guarantees", "status": "pending", "notes": ""},
    {"code": "3(ix)", "title": "Fraud reporting u/s 143(12)", "status": "pending", "notes": ""},
    {"code": "3(xiv)", "title": "Internal audit system", "status": "pending", "notes": ""},
    {"code": "3(xvii)", "title": "Cash losses", "status": "pending", "notes": ""},
    {"code": "3(xix)", "title": "Going concern capability", "status": "pending", "notes": ""},
]


class ChecklistIn(BaseModel):
    client_id: str
    framework: str = "CARO"
    entity_type: str = "pvt_ltd"
    fy: str
    items: Optional[list[Any]] = None


class ChecklistPatch(BaseModel):
    items: Optional[list[Any]] = None
    status: Optional[str] = None
    signoff: bool = False


def _checklist_out(row, clients=None):
    clients = clients or {}
    items = row.items or []
    done = sum(1 for i in items if (i.get("status") or "") in {"done", "na", "cleared"})
    pct = round((done / len(items)) * 100, 1) if items else 0
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "framework": row.framework,
        "entity_type": row.entity_type,
        "fy": row.fy,
        "items": items,
        "completion_pct": pct,
        "status": row.status,
        "signed_off_by": str(row.signed_off_by) if row.signed_off_by else None,
        "signed_off_at": _dt(row.signed_off_at),
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/checklists")
def list_checklists(
    request: Request,
    client_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("statutory_checklist")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, StatutoryChecklist, request.state.org_id)
    if client_id:
        q = q.filter(StatutoryChecklist.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    return [_checklist_out(r, clients) for r in q.order_by(StatutoryChecklist.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/checklists", status_code=201)
def create_checklist(
    payload: ChecklistIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("statutory_checklist")),
):
    _client(db, request.state.org_id, payload.client_id)
    items = payload.items
    if items is None:
        items = [dict(x) for x in CARO_TEMPLATE] if payload.framework.upper() == "CARO" else []
    row = StatutoryChecklist(
        org_id=request.state.org_id,
        created_by=user.id,
        client_id=payload.client_id,
        framework=payload.framework,
        entity_type=payload.entity_type,
        fy=payload.fy,
        items=items,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _checklist_out(row, _client_names(db, request.state.org_id))


@router.patch("/checklists/{checklist_id}")
def patch_checklist(
    checklist_id: str,
    payload: ChecklistPatch,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("statutory_checklist")),
):
    row = scoped(db, StatutoryChecklist, request.state.org_id).filter(StatutoryChecklist.id == checklist_id).first()
    if not row:
        raise HTTPException(404, "Checklist not found")
    values = payload.model_dump(exclude_unset=True)
    signoff = values.pop("signoff", False)
    if signoff:
        from app.utils.permissions import can_perform
        if not can_perform(user.role, "checklist:signoff"):
            raise HTTPException(403, "Only CA (Manager)+ can sign off checklists")
        row.signed_off_by = user.id
        row.signed_off_at = datetime.now(timezone.utc)
        row.status = "signed_off"
    for key, value in values.items():
        setattr(row, key, value)
    if row.items:
        done = sum(1 for i in row.items if (i.get("status") or "") in {"done", "na", "cleared"})
        row.completion_pct = round((done / len(row.items)) * 100, 2)
    db.commit()
    db.refresh(row)
    return _checklist_out(row, _client_names(db, request.state.org_id))


# ── ROC / XBRL Tracker ──────────────────────────────────────────────────────

class RocXbrlIn(BaseModel):
    client_id: str
    form_name: str
    fy: str
    due_date: Optional[date] = None
    validation_status: str = "pending"
    cost_audit_applicable: bool = False
    status: str = "open"
    notes: Optional[str] = None


class RocXbrlPatch(BaseModel):
    validation_status: Optional[str] = None
    status: Optional[str] = None
    due_date: Optional[date] = None
    cost_audit_applicable: Optional[bool] = None
    notes: Optional[str] = None


def _roc_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "form_name": row.form_name,
        "fy": row.fy,
        "due_date": _d(row.due_date),
        "validation_status": row.validation_status,
        "cost_audit_applicable": row.cost_audit_applicable,
        "status": row.status,
        "notes": row.notes,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/roc-xbrl")
def list_roc_xbrl(
    request: Request,
    client_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("roc_xbrl_tracker")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, RocXbrlFiling, request.state.org_id)
    if client_id:
        q = q.filter(RocXbrlFiling.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    return [_roc_out(r, clients) for r in q.order_by(RocXbrlFiling.due_date.asc().nullslast()).offset(skip).limit(limit).all()]


@router.post("/roc-xbrl", status_code=201)
def create_roc_xbrl(
    payload: RocXbrlIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("roc_xbrl_tracker")),
):
    _client(db, request.state.org_id, payload.client_id)
    row = RocXbrlFiling(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _roc_out(row, _client_names(db, request.state.org_id))


@router.patch("/roc-xbrl/{filing_id}")
def patch_roc_xbrl(
    filing_id: str,
    payload: RocXbrlPatch,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_feature("roc_xbrl_tracker")),
):
    row = scoped(db, RocXbrlFiling, request.state.org_id).filter(RocXbrlFiling.id == filing_id).first()
    if not row:
        raise HTTPException(404, "ROC/XBRL filing not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _roc_out(row, _client_names(db, request.state.org_id))


# ── E-Invoice / IRN Validation ──────────────────────────────────────────────

class EinvoiceIn(BaseModel):
    client_id: str
    invoice_no: str
    irn: Optional[str] = None
    status: str = "pending"
    turnover_threshold_hit: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


def _einvoice_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "invoice_no": row.invoice_no,
        "irn": row.irn,
        "status": row.status,
        "turnover_threshold_hit": row.turnover_threshold_hit,
        "details": row.details or {},
        "created_at": _dt(row.created_at),
    }


@router.get("/einvoice")
def list_einvoice(
    request: Request,
    client_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("einvoice_irn")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, EinvoiceValidation, request.state.org_id)
    if client_id:
        q = q.filter(EinvoiceValidation.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    return [_einvoice_out(r, clients) for r in q.order_by(EinvoiceValidation.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/einvoice", status_code=201)
def create_einvoice(
    payload: EinvoiceIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("einvoice_irn")),
):
    _client(db, request.state.org_id, payload.client_id)
    status_val = payload.status
    details = dict(payload.details or {})
    if payload.irn and len(payload.irn) >= 64:
        status_val = "valid"
        details["validated"] = True
    elif payload.irn:
        status_val = "invalid"
        details["reason"] = "IRN length/format check failed"
    row = EinvoiceValidation(
        org_id=request.state.org_id,
        created_by=user.id,
        client_id=payload.client_id,
        invoice_no=payload.invoice_no,
        irn=payload.irn,
        status=status_val,
        turnover_threshold_hit=payload.turnover_threshold_hit,
        details=details,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _einvoice_out(row, _client_names(db, request.state.org_id))


# ── Peer Review / QC ────────────────────────────────────────────────────────

class PeerReviewIn(BaseModel):
    cycle_label: str
    checklist: list[Any] = Field(default_factory=list)
    evidence_links: list[Any] = Field(default_factory=list)
    readiness_score: float = 0
    status: str = "open"


class PeerReviewPatch(BaseModel):
    checklist: Optional[list[Any]] = None
    evidence_links: Optional[list[Any]] = None
    readiness_score: Optional[float] = None
    status: Optional[str] = None


def _peer_out(row):
    return {
        "id": str(row.id),
        "cycle_label": row.cycle_label,
        "status": row.status,
        "checklist": row.checklist or [],
        "evidence_links": row.evidence_links or [],
        "readiness_score": _num(row.readiness_score),
        "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/peer-review")
def list_peer_review(
    request: Request,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("peer_review_qc")),
):
    skip, limit = _page(skip, limit)
    rows = scoped(db, PeerReviewPack, request.state.org_id).order_by(PeerReviewPack.created_at.desc()).offset(skip).limit(limit).all()
    return [_peer_out(r) for r in rows]


@router.post("/peer-review", status_code=201)
def create_peer_review(
    payload: PeerReviewIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_action("peer_review:manage")),
):
    row = PeerReviewPack(org_id=request.state.org_id, created_by=user.id, owner_user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _peer_out(row)


@router.patch("/peer-review/{pack_id}")
def patch_peer_review(
    pack_id: str,
    payload: PeerReviewPatch,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_action("peer_review:manage")),
):
    row = scoped(db, PeerReviewPack, request.state.org_id).filter(PeerReviewPack.id == pack_id).first()
    if not row:
        raise HTTPException(404, "Peer review pack not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _peer_out(row)


# ── SOP / Knowledge Base ────────────────────────────────────────────────────

class KnowledgeIn(BaseModel):
    topic: str
    title: str
    body: str
    tags: list[str] = Field(default_factory=list)
    published: bool = True


class KnowledgePatch(BaseModel):
    topic: Optional[str] = None
    title: Optional[str] = None
    body: Optional[str] = None
    tags: Optional[list[str]] = None
    published: Optional[bool] = None


def _knowledge_out(row):
    return {
        "id": str(row.id),
        "topic": row.topic,
        "title": row.title,
        "body": row.body,
        "tags": row.tags or [],
        "published": row.published,
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/knowledge")
def list_knowledge(
    request: Request,
    topic: str = "",
    q: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("sop_knowledge_base")),
):
    skip, limit = _page(skip, limit)
    query = scoped(db, KnowledgeArticle, request.state.org_id).filter(KnowledgeArticle.published.is_(True))
    if topic:
        query = query.filter(KnowledgeArticle.topic == topic)
    if q:
        term = f"%{q.strip()}%"
        from sqlalchemy import or_
        query = query.filter(or_(KnowledgeArticle.title.ilike(term), KnowledgeArticle.body.ilike(term)))
    return [_knowledge_out(r) for r in query.order_by(KnowledgeArticle.updated_at.desc()).offset(skip).limit(limit).all()]


@router.post("/knowledge", status_code=201)
def create_knowledge(
    payload: KnowledgeIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("sop_knowledge_base")),
):
    from app.utils.permissions import can_perform
    if user.role == "article" and not can_perform(user.role, "document:write"):
        # Articles can draft; managers publish. Keep published=False for articles.
        payload.published = False
    row = KnowledgeArticle(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _knowledge_out(row)


@router.patch("/knowledge/{article_id}")
def patch_knowledge(
    article_id: str,
    payload: KnowledgePatch,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("sop_knowledge_base")),
):
    row = scoped(db, KnowledgeArticle, request.state.org_id).filter(KnowledgeArticle.id == article_id).first()
    if not row:
        raise HTTPException(404, "Article not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("published") and user.role == "article":
        raise HTTPException(403, "Only CA (Manager)+ can publish SOP articles")
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _knowledge_out(row)


# ── Client Risk Scoring ─────────────────────────────────────────────────────

def _risk_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "score": _num(row.score),
        "tier": row.tier,
        "drivers": row.drivers or [],
        "computed_at": _dt(row.computed_at),
    }


@router.get("/risk-scores")
def list_risk_scores(
    request: Request,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(require_feature("client_risk_scoring")),
):
    skip, limit = _page(skip, limit)
    clients = _client_names(db, request.state.org_id)
    rows = scoped(db, ClientRiskScore, request.state.org_id).order_by(ClientRiskScore.score.desc()).offset(skip).limit(limit).all()
    return [_risk_out(r, clients) for r in rows]


@router.post("/risk-scores/recompute")
def recompute_risk_scores(
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_action("risk_score:view")),
):
    """Combine anomalies + overdue deadlines + billing outstanding into a per-client score."""
    org_id = request.state.org_id
    clients = scoped(db, Client, org_id).all()
    anomaly_counts = {}
    for flag in scoped(db, AnomalyFlag, org_id).filter(AnomalyFlag.reviewed.is_(False)).all():
        key = str(flag.client_id)
        anomaly_counts[key] = anomaly_counts.get(key, 0) + 1 + float(flag.risk_score or 0)

    overdue_deadlines = {}
    today = date.today()
    for dl in scoped(db, ComplianceDeadline, org_id).all():
        if dl.client_id and dl.deadline and dl.deadline < today and dl.status not in {"filed"}:
            overdue_deadlines[str(dl.client_id)] = overdue_deadlines.get(str(dl.client_id), 0) + 1

    billing_risk = {}
    for inv in scoped(db, PracticeInvoice, org_id).all():
        outstanding = float(inv.total or 0) - float(inv.amount_paid or 0)
        if outstanding > 0 and inv.status not in {"paid", "void"}:
            billing_risk[str(inv.client_id)] = billing_risk.get(str(inv.client_id), 0) + outstanding

    results = []
    for client in clients:
        cid = str(client.id)
        a = anomaly_counts.get(cid, 0)
        d = overdue_deadlines.get(cid, 0)
        b = billing_risk.get(cid, 0)
        score = min(100.0, round(a * 12 + d * 8 + min(b / 10000, 40), 2))
        tier = "green" if score < 25 else "amber" if score < 60 else "red"
        drivers = []
        if a:
            drivers.append({"factor": "open_anomalies", "weight": round(a * 12, 2)})
        if d:
            drivers.append({"factor": "overdue_deadlines", "weight": round(d * 8, 2)})
        if b:
            drivers.append({"factor": "billing_outstanding", "weight": round(min(b / 10000, 40), 2)})

        existing = scoped(db, ClientRiskScore, org_id).filter(ClientRiskScore.client_id == client.id).first()
        if existing:
            existing.score = score
            existing.tier = tier
            existing.drivers = drivers
            existing.computed_at = datetime.now(timezone.utc)
            row = existing
        else:
            row = ClientRiskScore(
                org_id=org_id,
                client_id=client.id,
                score=score,
                tier=tier,
                drivers=drivers,
            )
            db.add(row)
        results.append(row)
    db.commit()
    names = {str(c.id): c.name for c in clients}
    return [_risk_out(r, names) for r in results]


# ── Virtual CFO / MIS ───────────────────────────────────────────────────────

class MisIn(BaseModel):
    client_id: str
    period: str
    metrics: dict[str, Any] = Field(default_factory=dict)
    narrative: Optional[str] = None
    status: str = "draft"


class MisPatch(BaseModel):
    metrics: Optional[dict[str, Any]] = None
    narrative: Optional[str] = None
    status: Optional[str] = None
    publish: bool = False


def _mis_out(row, clients=None):
    clients = clients or {}
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "period": row.period,
        "metrics": row.metrics or {},
        "narrative": row.narrative,
        "status": row.status,
        "published_at": _dt(row.published_at),
        "created_at": _dt(row.created_at),
        "updated_at": _dt(row.updated_at),
    }


@router.get("/mis")
def list_mis(
    request: Request,
    client_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(require_feature("virtual_cfo_mis")),
):
    skip, limit = _page(skip, limit)
    q = scoped(db, MisDashboard, request.state.org_id)
    if client_id:
        q = q.filter(MisDashboard.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    return [_mis_out(r, clients) for r in q.order_by(MisDashboard.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/mis", status_code=201)
def create_mis(
    payload: MisIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_feature("virtual_cfo_mis")),
):
    _client(db, request.state.org_id, payload.client_id)
    row = MisDashboard(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _mis_out(row, _client_names(db, request.state.org_id))


@router.patch("/mis/{mis_id}")
def patch_mis(
    mis_id: str,
    payload: MisPatch,
    request: Request,
    db: Session = Depends(get_db),
    _=Depends(require_feature("virtual_cfo_mis")),
):
    row = scoped(db, MisDashboard, request.state.org_id).filter(MisDashboard.id == mis_id).first()
    if not row:
        raise HTTPException(404, "MIS dashboard not found")
    values = payload.model_dump(exclude_unset=True)
    publish = values.pop("publish", False)
    if publish:
        row.status = "published"
        row.published_at = datetime.now(timezone.utc)
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _mis_out(row, _client_names(db, request.state.org_id))


# ── Access matrix (self-documenting) ────────────────────────────────────────

@router.get("/access-matrix")
def access_matrix(_=Depends(get_current_user)):
    from app.utils.permissions import ACTION_PERMISSIONS, FEATURE_ROLES, TIER_LABELS
    return {
        "tiers": TIER_LABELS,
        "features": {k: list(v) for k, v in FEATURE_ROLES.items()},
        "actions": {k: list(v) for k, v in ACTION_PERMISSIONS.items()},
        "notes": [
            "Client is a separate portal auth context — not a users.role value.",
            "DSC vault, benchmarking, RFP, profitability, peer review are partner-only.",
            "Certificate/audit/notice/engagement sign-off is manager+ at API level.",
        ],
    }
