"""APIs for practice operations gaps: work, billing, portal, team, vault, imports, and reports."""
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.document import Document
from app.models.practice_ops import (
    AttendanceEntry, BillingPlan, ClientPortalContact, CredentialVaultItem,
    DaybookEntry, ImportJob, PaymentReceipt, PortalRequest, PracticeInvoice,
    PracticeTask, SavedView,
)
from app.models.user import User
from app.models.organization import Organization
from app.services.plan_limits import plan_limits, usage_status
from app.services.payment_gateway import (
    PaymentGatewayError, create_payment_link, parse_razorpay_payment_event,
    payment_gateway_status, verify_razorpay_webhook,
)
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped

router = APIRouter()
TASK_STATUSES = {"open", "in_progress", "review", "done", "blocked"}
INVOICE_STATUSES = {"draft", "sent", "part_paid", "paid", "void", "overdue"}
PORTAL_STATUSES = {"requested", "in_progress", "received", "approved", "closed"}
IMPORT_STATUSES = {"draft", "validated", "needs_mapping", "imported", "failed"}


def _page(skip: int, limit: int, max_limit: int = 5000):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > max_limit:
        raise HTTPException(422, f"limit must be between 1 and {max_limit}")
    return skip, limit


def _date(value):
    return value.isoformat() if value else None


def _datetime(value):
    return value.isoformat() if value else None


def _num(value):
    return float(value or 0)


def _client(db: Session, org_id, client_id: str):
    row = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not row:
        raise HTTPException(404, "Client not found")
    return row


def _user(db: Session, org_id, user_id: str):
    row = scoped(db, User, org_id).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(404, "User not found")
    return row


def _client_names(db: Session, org_id):
    return {str(row.id): row.name for row in scoped(db, Client, org_id).all()}


def _user_emails(db: Session, org_id):
    return {str(row.id): row.email for row in scoped(db, User, org_id).all()}


def _task_out(row, clients=None, users=None):
    clients = clients or {}
    users = users or {}
    checklist = row.checklist or []
    checklist_total = len(checklist)
    checklist_done = sum(1 for item in checklist if item.get("done"))
    today = date.today()
    days_until_due = (row.due_date - today).days if row.due_date else None
    return {
        "id": str(row.id),
        "client_id": str(row.client_id) if row.client_id else None,
        "client_name": clients.get(str(row.client_id), ""),
        "title": row.title,
        "service_type": row.service_type,
        "priority": row.priority,
        "status": row.status,
        "stage": row.stage,
        "due_date": _date(row.due_date),
        "assigned_to": str(row.assigned_to) if row.assigned_to else None,
        "assigned_to_email": users.get(str(row.assigned_to), ""),
        "reviewer_id": str(row.reviewer_id) if row.reviewer_id else None,
        "reviewer_email": users.get(str(row.reviewer_id), ""),
        "checklist": checklist,
        "checklist_done": checklist_done,
        "checklist_total": checklist_total,
        "checklist_progress": round((checklist_done / checklist_total) * 100) if checklist_total else 0,
        "tags": row.tags or [],
        "recurring_rule": row.recurring_rule or {},
        "notes": row.notes,
        "days_until_due": days_until_due,
        "is_overdue": bool(row.due_date and row.due_date < today and row.status != "done"),
        "completed_at": _datetime(row.completed_at),
        "created_at": _datetime(row.created_at),
        "updated_at": _datetime(row.updated_at),
    }


def _invoice_out(row, clients=None):
    clients = clients or {}
    outstanding = _num(row.total) - _num(row.amount_paid)
    today = date.today()
    days_overdue = (today - row.due_date).days if row.due_date and outstanding > 0 and row.due_date < today else 0
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "plan_id": str(row.plan_id) if row.plan_id else None,
        "invoice_no": row.invoice_no,
        "issue_date": _date(row.issue_date),
        "due_date": _date(row.due_date),
        "line_items": row.line_items or [],
        "subtotal": _num(row.subtotal),
        "tax": _num(row.tax),
        "total": _num(row.total),
        "amount_paid": _num(row.amount_paid),
        "outstanding": outstanding,
        "days_overdue": days_overdue,
        "status": row.status,
        "payment_link": row.payment_link,
        "created_at": _datetime(row.created_at),
    }


def _portal_request_out(row, clients=None, contacts=None):
    clients = clients or {}
    contacts = contacts or {}
    today = date.today()
    is_overdue = bool(row.due_date and row.due_date < today and row.status not in {"approved", "closed"})
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "contact_id": str(row.contact_id) if row.contact_id else None,
        "contact_name": contacts.get(str(row.contact_id), ""),
        "request_type": row.request_type,
        "title": row.title,
        "description": row.description,
        "due_date": _date(row.due_date),
        "status": row.status,
        "is_overdue": is_overdue,
        "days_overdue": (today - row.due_date).days if is_overdue else 0,
        "attachments": row.attachments or [],
        "response_summary": row.response_summary,
        "completed_at": _datetime(row.completed_at),
        "created_at": _datetime(row.created_at),
    }


class TaskRequest(BaseModel):
    client_id: Optional[str] = None
    title: str
    service_type: str = "compliance"
    priority: str = "medium"
    status: str = "open"
    stage: str = "maker"
    due_date: Optional[date] = None
    assigned_to: Optional[str] = None
    reviewer_id: Optional[str] = None
    checklist: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    recurring_rule: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None


class TaskUpdate(BaseModel):
    client_id: Optional[str] = None
    title: Optional[str] = None
    service_type: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None
    due_date: Optional[date] = None
    assigned_to: Optional[str] = None
    reviewer_id: Optional[str] = None
    checklist: Optional[list[dict[str, Any]]] = None
    tags: Optional[list[str]] = None
    recurring_rule: Optional[dict[str, Any]] = None
    notes: Optional[str] = None


class DaybookRequest(BaseModel):
    client_id: Optional[str] = None
    task_id: Optional[str] = None
    entry_date: date = Field(default_factory=date.today)
    activity_type: str = "follow_up"
    summary: str
    assigned_to: Optional[str] = None
    status: str = "open"


@router.get("/work/overview")
def work_overview(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    today = date.today()
    tasks = scoped(db, PracticeTask, request.state.org_id)
    task_rows = tasks.all()
    daybook = scoped(db, DaybookEntry, request.state.org_id).filter(DaybookEntry.entry_date == today)
    active = [row for row in task_rows if row.status in {"open", "in_progress", "review", "blocked"}]
    due_today = [row for row in active if row.due_date == today]
    due_week = [row for row in active if row.due_date and today <= row.due_date <= today + timedelta(days=7)]
    unassigned = [row for row in active if not row.assigned_to]
    by_priority: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in task_rows:
        by_priority[row.priority] = by_priority.get(row.priority, 0) + 1
        by_status[row.status] = by_status.get(row.status, 0) + 1
    return {
        "open_tasks": tasks.filter(PracticeTask.status.in_(["open", "in_progress", "review"])).count(),
        "overdue_tasks": tasks.filter(PracticeTask.status != "done", PracticeTask.due_date < today).count(),
        "due_today": len(due_today),
        "due_next_7_days": len(due_week),
        "blocked_tasks": tasks.filter(PracticeTask.status == "blocked").count(),
        "unassigned_tasks": len(unassigned),
        "review_queue": tasks.filter(PracticeTask.stage == "review", PracticeTask.status != "done").count(),
        "today_daybook": daybook.count(),
        "daybook_closed_today": daybook.filter(DaybookEntry.status.in_(["done", "closed"])).count(),
        "by_priority": by_priority,
        "by_status": by_status,
        "by_stage": {
            stage: count for stage, count in tasks.with_entities(PracticeTask.stage, func.count(PracticeTask.id)).group_by(PracticeTask.stage).all()
        },
    }


@router.get("/work/tasks")
def list_tasks(
    request: Request,
    status: str = "",
    client_id: str = "",
    priority: str = "",
    stage: str = "",
    assigned_to: str = "",
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = _page(skip, limit)
    query = scoped(db, PracticeTask, request.state.org_id)
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if any(item not in TASK_STATUSES for item in statuses):
            raise HTTPException(422, "Invalid task status")
        query = query.filter(PracticeTask.status.in_(statuses))
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(PracticeTask.client_id == client_id)
    if priority:
        query = query.filter(PracticeTask.priority == priority)
    if stage:
        query = query.filter(PracticeTask.stage == stage)
    if assigned_to:
        _user(db, request.state.org_id, assigned_to)
        query = query.filter(PracticeTask.assigned_to == assigned_to)
    if due_from:
        query = query.filter(PracticeTask.due_date >= due_from)
    if due_to:
        query = query.filter(PracticeTask.due_date <= due_to)
    clients = _client_names(db, request.state.org_id)
    users = _user_emails(db, request.state.org_id)
    rows = query.order_by(PracticeTask.due_date.asc().nullslast(), PracticeTask.created_at.desc()).offset(skip).limit(limit).all()
    return [_task_out(row, clients, users) for row in rows]


@router.post("/work/tasks", status_code=201)
def create_task(payload: TaskRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.client_id:
        _client(db, request.state.org_id, payload.client_id)
    if payload.assigned_to:
        _user(db, request.state.org_id, payload.assigned_to)
    if payload.reviewer_id:
        _user(db, request.state.org_id, payload.reviewer_id)
    if payload.status not in TASK_STATUSES:
        raise HTTPException(422, "Invalid task status")
    row = PracticeTask(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _task_out(row, _client_names(db, request.state.org_id), _user_emails(db, request.state.org_id))


@router.patch("/work/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, PracticeTask, request.state.org_id).filter(PracticeTask.id == task_id).first()
    if not row:
        raise HTTPException(404, "Task not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("client_id"):
        _client(db, request.state.org_id, values["client_id"])
    if values.get("assigned_to"):
        _user(db, request.state.org_id, values["assigned_to"])
    if values.get("reviewer_id"):
        _user(db, request.state.org_id, values["reviewer_id"])
    if values.get("status") and values["status"] not in TASK_STATUSES:
        raise HTTPException(422, "Invalid task status")
    for key, value in values.items():
        setattr(row, key, value)
    if values.get("status") == "done" and not row.completed_at:
        row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _task_out(row, _client_names(db, request.state.org_id), _user_emails(db, request.state.org_id))


@router.get("/work/daybook")
def list_daybook(
    request: Request,
    target_date: Optional[date] = None,
    client_id: str = "",
    status: str = "",
    activity_type: str = "",
    assigned_to: str = "",
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = _page(skip, limit)
    day = target_date or date.today()
    query = scoped(db, DaybookEntry, request.state.org_id).filter(DaybookEntry.entry_date == day)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(DaybookEntry.client_id == client_id)
    if status:
        query = query.filter(DaybookEntry.status == status)
    if activity_type:
        query = query.filter(DaybookEntry.activity_type == activity_type)
    if assigned_to:
        _user(db, request.state.org_id, assigned_to)
        query = query.filter(DaybookEntry.assigned_to == assigned_to)
    rows = query.order_by(DaybookEntry.created_at.desc()).offset(skip).limit(limit).all()
    clients = _client_names(db, request.state.org_id)
    users = _user_emails(db, request.state.org_id)
    return [{
        "id": str(row.id), "client_id": str(row.client_id) if row.client_id else None,
        "client_name": clients.get(str(row.client_id), ""), "task_id": str(row.task_id) if row.task_id else None,
        "entry_date": _date(row.entry_date), "activity_type": row.activity_type,
        "summary": row.summary, "assigned_to": str(row.assigned_to) if row.assigned_to else None,
        "assigned_to_email": users.get(str(row.assigned_to), ""), "status": row.status,
        "created_at": _datetime(row.created_at),
    } for row in rows]


@router.post("/work/daybook", status_code=201)
def create_daybook(payload: DaybookRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.client_id:
        _client(db, request.state.org_id, payload.client_id)
    if payload.assigned_to:
        _user(db, request.state.org_id, payload.assigned_to)
    row = DaybookEntry(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id)}


class BillingPlanRequest(BaseModel):
    client_id: str
    name: str
    service_scope: list[str] = Field(default_factory=list)
    frequency: str = "monthly"
    amount: float = 0
    tax_rate: float = 18
    next_invoice_date: Optional[date] = None
    active: bool = True


class InvoiceRequest(BaseModel):
    client_id: str
    plan_id: Optional[str] = None
    invoice_no: Optional[str] = None
    issue_date: date = Field(default_factory=date.today)
    due_date: Optional[date] = None
    line_items: list[dict[str, Any]] = Field(default_factory=list)
    tax_rate: float = 18
    status: str = "sent"
    payment_link: Optional[str] = None


class InvoiceUpdate(BaseModel):
    due_date: Optional[date] = None
    status: Optional[str] = None
    payment_link: Optional[str] = None


class PaymentRequest(BaseModel):
    paid_at: date = Field(default_factory=date.today)
    amount: float
    mode: str = "bank_transfer"
    reference: Optional[str] = None
    notes: Optional[str] = None


def _invoice_totals(line_items, tax_rate: float):
    subtotal = 0.0
    for item in line_items or []:
        if "amount" in item:
            subtotal += float(item.get("amount") or 0)
        else:
            subtotal += float(item.get("quantity") or 1) * float(item.get("rate") or 0)
    tax = round(subtotal * float(tax_rate or 0) / 100, 2)
    return round(subtotal, 2), tax, round(subtotal + tax, 2)


@router.get("/billing/overview")
def billing_overview(request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    invoices = scoped(db, PracticeInvoice, request.state.org_id).all()
    today = date.today()
    outstanding = sum(max(_num(row.total) - _num(row.amount_paid), 0) for row in invoices if row.status != "paid")
    overdue = sum(max(_num(row.total) - _num(row.amount_paid), 0) for row in invoices if row.status != "paid" and row.due_date < today)
    collected = sum(_num(row.amount_paid) for row in invoices)
    by_status: dict[str, int] = {}
    ageing = {"current": 0.0, "1_30": 0.0, "31_60": 0.0, "61_90": 0.0, "90_plus": 0.0}
    for row in invoices:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        balance = max(_num(row.total) - _num(row.amount_paid), 0)
        if balance <= 0:
            continue
        if not row.due_date or row.due_date >= today:
            ageing["current"] += balance
            continue
        days = (today - row.due_date).days
        if days <= 30:
            ageing["1_30"] += balance
        elif days <= 60:
            ageing["31_60"] += balance
        elif days <= 90:
            ageing["61_90"] += balance
        else:
            ageing["90_plus"] += balance
    plans = scoped(db, BillingPlan, request.state.org_id)
    return {
        "invoice_count": len(invoices),
        "outstanding": outstanding,
        "overdue": overdue,
        "collected": collected,
        "collection_rate": round((collected / sum(_num(row.total) for row in invoices)) * 100, 1) if invoices else 0,
        "by_status": by_status,
        "ageing": ageing,
        "active_plans": plans.filter(BillingPlan.active.is_(True)).count(),
        "plans_due_next_30": plans.filter(
            BillingPlan.active.is_(True),
            BillingPlan.next_invoice_date <= today + timedelta(days=30),
        ).count(),
    }


@router.get("/billing/plan-usage")
def billing_plan_usage(request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")
    limits = plan_limits(org.plan)
    period_start = date.today().replace(day=1)
    period_start_dt = datetime.combine(period_start, datetime.min.time(), tzinfo=timezone.utc)
    usage = {
        "clients": scoped(db, Client, request.state.org_id).count(),
        "users": scoped(db, User, request.state.org_id).count(),
        "documents_per_month": scoped(db, Document, request.state.org_id).filter(Document.created_at >= period_start_dt).count(),
        "ai_queries_per_month": 0,
        "storage_gb": round(
            sum(float(row.file_size_bytes or 0) for row in scoped(db, Document, request.state.org_id).all()) / (1024 ** 3),
            3,
        ),
    }
    return {
        "plan": org.plan,
        "period_start": period_start.isoformat(),
        "limits": limits,
        "usage": usage,
        "status": {key: usage_status(value, limits.get(key)) for key, value in usage.items()},
    }


@router.get("/billing/plans")
def billing_plans(request: Request, client_id: str = "", active: str = "", db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    query = scoped(db, BillingPlan, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(BillingPlan.client_id == client_id)
    if active:
        query = query.filter(BillingPlan.active.is_(active.lower() == "true"))
    clients = _client_names(db, request.state.org_id)
    return [{
        "id": str(row.id), "client_id": str(row.client_id), "client_name": clients.get(str(row.client_id), ""),
        "name": row.name, "service_scope": row.service_scope or [], "frequency": row.frequency,
        "amount": _num(row.amount), "tax_rate": _num(row.tax_rate),
        "next_invoice_date": _date(row.next_invoice_date), "active": row.active,
    } for row in query.order_by(BillingPlan.created_at.desc()).all()]


@router.post("/billing/plans", status_code=201)
def create_billing_plan(payload: BillingPlanRequest, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    row = BillingPlan(org_id=request.state.org_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id)}


@router.get("/billing/invoices")
def invoices(
    request: Request,
    status: str = "",
    client_id: str = "",
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 2000,
    db: Session = Depends(get_db),
    _=Depends(require_role(["partner", "manager"])),
):
    query = scoped(db, PracticeInvoice, request.state.org_id)
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if any(item not in INVOICE_STATUSES for item in statuses):
            raise HTTPException(422, "Invalid invoice status")
        query = query.filter(PracticeInvoice.status.in_(statuses))
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(PracticeInvoice.client_id == client_id)
    if due_from:
        query = query.filter(PracticeInvoice.due_date >= due_from)
    if due_to:
        query = query.filter(PracticeInvoice.due_date <= due_to)
    clients = _client_names(db, request.state.org_id)
    limit = max(1, min(limit, 5000))
    skip = max(0, skip)
    rows = query.order_by(PracticeInvoice.due_date.asc()).offset(skip).limit(limit).all()
    return [_invoice_out(row, clients) for row in rows]


@router.get("/billing/payments")
def payments(request: Request, client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    skip, limit = _page(skip, limit)
    query = scoped(db, PaymentReceipt, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(PaymentReceipt.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    invoice_nos = {
        str(row.id): row.invoice_no
        for row in scoped(db, PracticeInvoice, request.state.org_id).all()
    }
    rows = query.order_by(PaymentReceipt.paid_at.desc(), PaymentReceipt.created_at.desc()).offset(skip).limit(limit).all()
    return [{
        "id": str(row.id),
        "invoice_id": str(row.invoice_id),
        "invoice_no": invoice_nos.get(str(row.invoice_id), ""),
        "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id), ""),
        "paid_at": _date(row.paid_at),
        "amount": _num(row.amount),
        "mode": row.mode,
        "reference": row.reference,
        "notes": row.notes,
        "created_at": _datetime(row.created_at),
    } for row in rows]


@router.get("/billing/gateway-status")
def billing_gateway_status(_=Depends(require_role(["partner", "manager"]))):
    return payment_gateway_status()


@router.post("/billing/invoices", status_code=201)
def create_invoice(payload: InvoiceRequest, request: Request, db: Session = Depends(get_db), user=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    if payload.status not in INVOICE_STATUSES:
        raise HTTPException(422, "Invalid invoice status")
    line_items = payload.line_items or [{"description": "Professional fees", "amount": 0}]
    subtotal, tax, total = _invoice_totals(line_items, payload.tax_rate)
    invoice_no = payload.invoice_no or f"INV-{date.today().strftime('%Y%m')}-{scoped(db, PracticeInvoice, request.state.org_id).count() + 1:04d}"
    if scoped(db, PracticeInvoice, request.state.org_id).filter(PracticeInvoice.invoice_no == invoice_no).first():
        raise HTTPException(409, "Invoice number already exists")
    row = PracticeInvoice(
        org_id=request.state.org_id, client_id=payload.client_id, plan_id=payload.plan_id,
        invoice_no=invoice_no, issue_date=payload.issue_date,
        due_date=payload.due_date or payload.issue_date + timedelta(days=15),
        line_items=line_items, subtotal=subtotal, tax=tax, total=total,
        status=payload.status, payment_link=payload.payment_link, created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _invoice_out(row, _client_names(db, request.state.org_id))


@router.post("/billing/invoices/{invoice_id}/payment-link")
def create_invoice_payment_link(invoice_id: str, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    invoice = scoped(db, PracticeInvoice, request.state.org_id).filter(PracticeInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    client = _client(db, request.state.org_id, str(invoice.client_id))
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    try:
        link = create_payment_link(invoice, client, org)
    except PaymentGatewayError as exc:
        raise HTTPException(503, str(exc)) from exc
    invoice.payment_link = link.get("payment_link")
    db.commit()
    db.refresh(invoice)
    return {
        "invoice": _invoice_out(invoice, _client_names(db, request.state.org_id)),
        "gateway": {
            "provider": link.get("provider"),
            "provider_reference": link.get("provider_reference"),
            "status": link.get("status"),
        },
    }


@router.patch("/billing/invoices/{invoice_id}")
def update_invoice(invoice_id: str, payload: InvoiceUpdate, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, PracticeInvoice, request.state.org_id).filter(PracticeInvoice.id == invoice_id).first()
    if not row:
        raise HTTPException(404, "Invoice not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "status" and value not in INVOICE_STATUSES:
            raise HTTPException(422, "Invalid invoice status")
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _invoice_out(row, _client_names(db, request.state.org_id))


@router.post("/billing/invoices/{invoice_id}/payments", status_code=201)
def record_payment(invoice_id: str, payload: PaymentRequest, request: Request, db: Session = Depends(get_db), user=Depends(require_role(["partner", "manager"]))):
    invoice = scoped(db, PracticeInvoice, request.state.org_id).filter(PracticeInvoice.id == invoice_id).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    if payload.amount <= 0:
        raise HTTPException(422, "Payment amount must be positive")
    if _num(invoice.amount_paid) + payload.amount > _num(invoice.total) + 1:
        raise HTTPException(422, "Payment exceeds invoice total")
    receipt = PaymentReceipt(
        org_id=request.state.org_id, invoice_id=invoice.id, client_id=invoice.client_id,
        created_by=user.id, **payload.model_dump(),
    )
    invoice.amount_paid = _num(invoice.amount_paid) + payload.amount
    invoice.status = "paid" if _num(invoice.amount_paid) >= _num(invoice.total) else "part_paid"
    db.add(receipt)
    db.commit()
    return {"id": str(receipt.id), "invoice": _invoice_out(invoice, _client_names(db, request.state.org_id))}


@router.post("/billing/webhooks/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature")
    try:
        verified = verify_razorpay_webhook(raw_body, signature)
    except PaymentGatewayError as exc:
        raise HTTPException(503, str(exc)) from exc
    if not verified:
        raise HTTPException(400, "Invalid Razorpay signature")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid webhook payload") from exc
    event = parse_razorpay_payment_event(payload)
    if event["event"] not in {"payment_link.paid", "payment.captured"}:
        return {"status": "ignored", "event": event["event"]}
    if not event.get("invoice_id") or event["amount"] <= 0:
        raise HTTPException(422, "Webhook is missing invoice metadata")
    invoice = db.query(PracticeInvoice).filter(
        PracticeInvoice.id == event["invoice_id"],
        PracticeInvoice.org_id == event["org_id"],
    ).first()
    if not invoice:
        raise HTTPException(404, "Invoice not found")
    reference = event.get("payment_id") or event.get("payment_link_id")
    existing = db.query(PaymentReceipt).filter(
        PaymentReceipt.org_id == invoice.org_id,
        PaymentReceipt.reference == reference,
    ).first()
    if existing:
        return {"status": "duplicate_ignored", "payment_id": reference}
    amount = min(event["amount"], max(float(invoice.total or 0) - float(invoice.amount_paid or 0), 0))
    if amount <= 0:
        return {"status": "already_paid", "payment_id": reference}
    receipt = PaymentReceipt(
        org_id=invoice.org_id,
        invoice_id=invoice.id,
        client_id=invoice.client_id,
        paid_at=date.today(),
        amount=amount,
        mode=f"razorpay:{event.get('method') or 'payment'}",
        reference=reference,
        notes=f"Razorpay webhook {event['event']}",
    )
    invoice.amount_paid = float(invoice.amount_paid or 0) + amount
    invoice.status = "paid" if float(invoice.amount_paid or 0) >= float(invoice.total or 0) else "part_paid"
    db.add(receipt)
    db.commit()
    return {"status": "recorded", "receipt_id": str(receipt.id), "invoice_id": str(invoice.id)}


class PortalContactRequest(BaseModel):
    client_id: str
    name: str
    email: str
    phone: Optional[str] = None
    role: str = "client_user"
    access_status: str = "invited"


class PortalRequestIn(BaseModel):
    client_id: str
    contact_id: Optional[str] = None
    request_type: str = "document"
    title: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    status: str = "requested"
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class PortalRequestUpdate(BaseModel):
    status: Optional[str] = None
    response_summary: Optional[str] = None
    attachments: Optional[list[dict[str, Any]]] = None


@router.get("/portal/overview")
def portal_overview(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    today = date.today()
    requests = scoped(db, PortalRequest, request.state.org_id).all()
    contacts = scoped(db, ClientPortalContact, request.state.org_id).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in requests:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_type[row.request_type] = by_type.get(row.request_type, 0) + 1
    active_statuses = {"requested", "in_progress", "received"}
    return {
        "contacts": len(contacts),
        "active_contacts": sum(1 for row in contacts if row.access_status in {"invited", "active"}),
        "requests": len(requests),
        "open_requests": sum(1 for row in requests if row.status in active_statuses),
        "overdue_requests": sum(1 for row in requests if row.due_date and row.due_date < today and row.status in active_statuses),
        "due_next_7_days": sum(1 for row in requests if row.due_date and today <= row.due_date <= today + timedelta(days=7) and row.status in active_statuses),
        "received_pending_review": sum(1 for row in requests if row.status == "received"),
        "by_status": by_status,
        "by_type": by_type,
    }


@router.get("/portal/contacts")
def portal_contacts(
    request: Request,
    client_id: str = "",
    access_status: str = "",
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = _page(skip, limit)
    query = scoped(db, ClientPortalContact, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(ClientPortalContact.client_id == client_id)
    if access_status:
        query = query.filter(ClientPortalContact.access_status == access_status)
    clients = _client_names(db, request.state.org_id)
    return [{
        "id": str(row.id), "client_id": str(row.client_id), "client_name": clients.get(str(row.client_id), ""),
        "name": row.name, "email": row.email, "phone": row.phone, "role": row.role,
        "access_status": row.access_status, "last_login_at": _datetime(row.last_login_at),
    } for row in query.order_by(ClientPortalContact.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/portal/contacts", status_code=201)
def create_portal_contact(payload: PortalContactRequest, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    if scoped(db, ClientPortalContact, request.state.org_id).filter(ClientPortalContact.client_id == payload.client_id, ClientPortalContact.email == payload.email).first():
        raise HTTPException(409, "Portal contact email already exists for this client")
    row = ClientPortalContact(org_id=request.state.org_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id)}


@router.get("/portal/requests")
def portal_requests(
    request: Request,
    status: str = "",
    client_id: str = "",
    request_type: str = "",
    contact_id: str = "",
    due_to: Optional[date] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = _page(skip, limit)
    query = scoped(db, PortalRequest, request.state.org_id)
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if any(item not in PORTAL_STATUSES for item in statuses):
            raise HTTPException(422, "Invalid portal request status")
        query = query.filter(PortalRequest.status.in_(statuses))
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(PortalRequest.client_id == client_id)
    if request_type:
        query = query.filter(PortalRequest.request_type == request_type)
    if contact_id:
        query = query.filter(PortalRequest.contact_id == contact_id)
    if due_to:
        query = query.filter(PortalRequest.due_date <= due_to)
    clients = _client_names(db, request.state.org_id)
    contacts = {str(row.id): row.name for row in scoped(db, ClientPortalContact, request.state.org_id).all()}
    rows = query.order_by(PortalRequest.due_date.asc().nullslast(), PortalRequest.created_at.desc()).offset(skip).limit(limit).all()
    return [_portal_request_out(row, clients, contacts) for row in rows]


@router.post("/portal/requests", status_code=201)
def create_portal_request(payload: PortalRequestIn, request: Request, db: Session = Depends(get_db), user=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    if payload.status not in PORTAL_STATUSES:
        raise HTTPException(422, "Invalid portal request status")
    if payload.contact_id and not scoped(db, ClientPortalContact, request.state.org_id).filter(ClientPortalContact.id == payload.contact_id, ClientPortalContact.client_id == payload.client_id).first():
        raise HTTPException(404, "Portal contact not found for client")
    row = PortalRequest(org_id=request.state.org_id, created_by=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _portal_request_out(row, _client_names(db, request.state.org_id), {})


@router.patch("/portal/requests/{request_id}")
def update_portal_request(request_id: str, payload: PortalRequestUpdate, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, PortalRequest, request.state.org_id).filter(PortalRequest.id == request_id).first()
    if not row:
        raise HTTPException(404, "Portal request not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "status" and value not in PORTAL_STATUSES:
            raise HTTPException(422, "Invalid portal request status")
        setattr(row, key, value)
    if payload.status in ("received", "approved", "closed") and not row.completed_at:
        row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _portal_request_out(row, _client_names(db, request.state.org_id), {})


@router.get("/portal/client/{client_id}/snapshot")
def portal_client_snapshot(client_id: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _client(db, request.state.org_id, client_id)
    client_invoices = scoped(db, PracticeInvoice, request.state.org_id).filter(PracticeInvoice.client_id == client_id).all()
    return {
        "requests": portal_requests(request, client_id=client_id, db=db, _=_),
        "open_deadlines": scoped(db, ComplianceDeadline, request.state.org_id).filter(
            ComplianceDeadline.client_id == client_id, ComplianceDeadline.status != "filed",
        ).count(),
        "documents": scoped(db, Document, request.state.org_id).filter(Document.client_id == client_id).count(),
        "outstanding": sum(max(_num(row.total) - _num(row.amount_paid), 0) for row in client_invoices if row.status != "paid"),
    }


class AttendanceRequest(BaseModel):
    user_id: Optional[str] = None
    work_date: date = Field(default_factory=date.today)
    status: str = "present"
    hours_available: float = 8
    hours_booked: float = 0
    notes: Optional[str] = None


@router.get("/team/overview")
def team_overview(request: Request, target_date: Optional[date] = None, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    day = target_date or date.today()
    users = scoped(db, User, request.state.org_id).all()
    attendance = scoped(db, AttendanceEntry, request.state.org_id).filter(AttendanceEntry.work_date == day).all()
    booked_by_user = {str(row.user_id): _num(row.hours_booked) for row in attendance}
    available_by_user = {str(row.user_id): _num(row.hours_available) for row in attendance}
    status_by_user = {str(row.user_id): row.status for row in attendance}
    attendance_by_status: dict[str, int] = {}
    role_counts: dict[str, int] = {}
    for row in attendance:
        attendance_by_status[row.status] = attendance_by_status.get(row.status, 0) + 1
    for user in users:
        role_counts[user.role] = role_counts.get(user.role, 0) + 1
    tasks_by_user = {
        str(user_id): count for user_id, count in scoped(db, PracticeTask, request.state.org_id)
        .filter(PracticeTask.status != "done", PracticeTask.assigned_to.isnot(None))
        .with_entities(PracticeTask.assigned_to, func.count(PracticeTask.id))
        .group_by(PracticeTask.assigned_to).all()
    }
    hours_available = sum(available_by_user.values())
    hours_booked = sum(booked_by_user.values())
    return {
        "staff_count": len(users),
        "present_count": sum(1 for row in attendance if row.status == "present"),
        "hours_available": hours_available,
        "hours_booked": hours_booked,
        "utilization": round((hours_booked / hours_available) * 100, 1) if hours_available else 0,
        "attendance_by_status": attendance_by_status,
        "role_counts": role_counts,
        "overloaded_count": sum(1 for user in users if available_by_user.get(str(user.id), 8) and booked_by_user.get(str(user.id), 0) / available_by_user.get(str(user.id), 8) >= 1),
        "underutilized_count": sum(1 for user in users if available_by_user.get(str(user.id), 8) and booked_by_user.get(str(user.id), 0) / available_by_user.get(str(user.id), 8) < .5),
        "capacity": [{
            "user_id": str(user.id), "email": user.email, "role": user.role,
            "attendance_status": status_by_user.get(str(user.id), "not_marked"),
            "hours_available": available_by_user.get(str(user.id), 8),
            "hours_booked": booked_by_user.get(str(user.id), 0),
            "utilization": round((booked_by_user.get(str(user.id), 0) / available_by_user.get(str(user.id), 8)) * 100, 1) if available_by_user.get(str(user.id), 8) else 0,
            "open_tasks": tasks_by_user.get(str(user.id), 0),
        } for user in users],
    }


@router.get("/team/attendance")
def list_attendance(
    request: Request,
    target_date: Optional[date] = None,
    user_id: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    _=Depends(require_role(["partner", "manager"])),
):
    day = target_date or date.today()
    users = _user_emails(db, request.state.org_id)
    query = scoped(db, AttendanceEntry, request.state.org_id).filter(AttendanceEntry.work_date == day)
    if user_id:
        _user(db, request.state.org_id, user_id)
        query = query.filter(AttendanceEntry.user_id == user_id)
    if status:
        query = query.filter(AttendanceEntry.status == status)
    rows = query.order_by(AttendanceEntry.created_at.desc()).all()
    return [{
        "id": str(row.id), "user_id": str(row.user_id), "email": users.get(str(row.user_id), ""),
        "work_date": _date(row.work_date), "status": row.status,
        "hours_available": _num(row.hours_available), "hours_booked": _num(row.hours_booked),
        "utilization": round((_num(row.hours_booked) / _num(row.hours_available)) * 100, 1) if _num(row.hours_available) else 0,
        "notes": row.notes,
        "created_at": _datetime(row.created_at),
    } for row in rows]


@router.post("/team/attendance", status_code=201)
def upsert_attendance(payload: AttendanceRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    user_id = payload.user_id or str(user.id)
    _user(db, request.state.org_id, user_id)
    row = scoped(db, AttendanceEntry, request.state.org_id).filter(
        AttendanceEntry.user_id == user_id, AttendanceEntry.work_date == payload.work_date,
    ).first()
    if not row:
        row = AttendanceEntry(org_id=request.state.org_id, user_id=user_id, work_date=payload.work_date)
        db.add(row)
    for key, value in payload.model_dump(exclude={"user_id", "work_date"}).items():
        setattr(row, key, value)
    db.commit()
    return {"id": str(row.id)}


class VaultItemRequest(BaseModel):
    client_id: Optional[str] = None
    label: str
    credential_type: str = "portal"
    username: Optional[str] = None
    secret_hint: Optional[str] = None
    storage_reference: Optional[str] = None
    owner_user_id: Optional[str] = None
    expires_on: Optional[date] = None
    rotation_status: str = "current"
    notes: Optional[str] = None


class VaultItemUpdate(BaseModel):
    rotation_status: Optional[str] = None
    expires_on: Optional[date] = None
    notes: Optional[str] = None
    last_used_now: bool = False


def _mask_secret(secret: Optional[str]):
    if not secret:
        return None
    return f"{'*' * max(len(secret) - 4, 4)}{secret[-4:]}"


def _vault_item_out(row, clients=None, users=None):
    clients = clients or {}
    users = users or {}
    today = date.today()
    days_to_expiry = (row.expires_on - today).days if row.expires_on else None
    return {
        "id": str(row.id), "client_id": str(row.client_id) if row.client_id else None,
        "client_name": clients.get(str(row.client_id), ""), "label": row.label,
        "credential_type": row.credential_type, "username": row.username,
        "masked_secret": row.masked_secret, "storage_reference": row.storage_reference,
        "owner_user_id": str(row.owner_user_id) if row.owner_user_id else None,
        "owner_email": users.get(str(row.owner_user_id), ""), "expires_on": _date(row.expires_on),
        "days_to_expiry": days_to_expiry,
        "is_expired": bool(days_to_expiry is not None and days_to_expiry < 0),
        "is_expiring_soon": bool(days_to_expiry is not None and 0 <= days_to_expiry <= 30),
        "rotation_status": row.rotation_status, "last_used_at": _datetime(row.last_used_at),
        "notes": row.notes,
    }


@router.get("/vault/overview")
def vault_overview(request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    today = date.today()
    rows = scoped(db, CredentialVaultItem, request.state.org_id).all()
    by_type: dict[str, int] = {}
    by_rotation: dict[str, int] = {}
    for row in rows:
        by_type[row.credential_type] = by_type.get(row.credential_type, 0) + 1
        by_rotation[row.rotation_status] = by_rotation.get(row.rotation_status, 0) + 1
    return {
        "total": len(rows),
        "firm_items": sum(1 for row in rows if not row.client_id),
        "client_items": sum(1 for row in rows if row.client_id),
        "expired": sum(1 for row in rows if row.expires_on and row.expires_on < today),
        "expiring_30_days": sum(1 for row in rows if row.expires_on and today <= row.expires_on <= today + timedelta(days=30)),
        "rotation_due": sum(1 for row in rows if row.rotation_status != "current"),
        "unowned": sum(1 for row in rows if not row.owner_user_id),
        "by_type": by_type,
        "by_rotation": by_rotation,
    }


@router.get("/vault/items")
def vault_items(
    request: Request,
    client_id: str = "",
    credential_type: str = "",
    rotation_status: str = "",
    owner_user_id: str = "",
    expiring_within_days: Optional[int] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    _=Depends(require_role(["partner", "manager"])),
):
    skip, limit = _page(skip, limit)
    query = scoped(db, CredentialVaultItem, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(CredentialVaultItem.client_id == client_id)
    if credential_type:
        query = query.filter(CredentialVaultItem.credential_type == credential_type)
    if rotation_status:
        query = query.filter(CredentialVaultItem.rotation_status == rotation_status)
    if owner_user_id:
        _user(db, request.state.org_id, owner_user_id)
        query = query.filter(CredentialVaultItem.owner_user_id == owner_user_id)
    if expiring_within_days is not None:
        query = query.filter(CredentialVaultItem.expires_on <= date.today() + timedelta(days=max(expiring_within_days, 0)))
    clients = _client_names(db, request.state.org_id)
    users = _user_emails(db, request.state.org_id)
    return [_vault_item_out(row, clients, users) for row in query.order_by(CredentialVaultItem.expires_on.asc().nullslast()).offset(skip).limit(limit).all()]


@router.post("/vault/items", status_code=201)
def create_vault_item(payload: VaultItemRequest, request: Request, db: Session = Depends(get_db), user=Depends(require_role(["partner", "manager"]))):
    if payload.client_id:
        _client(db, request.state.org_id, payload.client_id)
    if payload.owner_user_id:
        _user(db, request.state.org_id, payload.owner_user_id)
    row = CredentialVaultItem(
        org_id=request.state.org_id, created_by=user.id,
        masked_secret=_mask_secret(payload.secret_hint),
        **payload.model_dump(exclude={"secret_hint"}),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id)}


@router.patch("/vault/items/{item_id}")
def update_vault_item(item_id: str, payload: VaultItemUpdate, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, CredentialVaultItem, request.state.org_id).filter(CredentialVaultItem.id == item_id).first()
    if not row:
        raise HTTPException(404, "Vault item not found")
    values = payload.model_dump(exclude_unset=True)
    if values.pop("last_used_now", False):
        row.last_used_at = datetime.now(timezone.utc)
    if values.get("rotation_status") and values["rotation_status"] not in {"current", "due", "rotating", "expired", "revoked"}:
        raise HTTPException(422, "Invalid rotation status")
    for key, value in values.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _vault_item_out(row, _client_names(db, request.state.org_id), _user_emails(db, request.state.org_id))


REQUIRED_IMPORT_FIELDS = {
    "tally_vouchers": ["date", "voucher_no", "party_name", "amount"],
    "gst_2b": ["gstin", "invoice_no", "invoice_date", "taxable_value", "tax_amount"],
    "client_master": ["name"],
    "billing": ["client_name", "amount"],
    "attendance": ["email", "work_date"],
}


class ImportJobRequest(BaseModel):
    client_id: Optional[str] = None
    import_type: str = "tally_vouchers"
    source_name: str
    mapping: dict[str, str] = Field(default_factory=dict)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


def _import_job_out(row, clients=None):
    clients = clients or {}
    invalid = max((row.records_total or 0) - (row.records_valid or 0), 0)
    return {
        "id": str(row.id), "client_id": str(row.client_id) if row.client_id else None,
        "client_name": clients.get(str(row.client_id), ""), "import_type": row.import_type,
        "source_name": row.source_name, "status": row.status, "mapping": row.mapping,
        "sample_rows": row.sample_rows, "validation_errors": row.validation_errors,
        "records_total": row.records_total, "records_valid": row.records_valid,
        "records_invalid": invalid, "records_imported": row.records_imported,
        "valid_ratio": round(((row.records_valid or 0) / row.records_total) * 100, 1) if row.records_total else 0,
        "created_at": _datetime(row.created_at), "completed_at": _datetime(row.completed_at),
    }


@router.get("/imports/config")
def imports_config(_=Depends(get_current_user)):
    return {
        "import_types": [{
            "key": key,
            "required_fields": fields,
            "sample_row": {field: f"sample_{field}" for field in fields},
        } for key, fields in REQUIRED_IMPORT_FIELDS.items()],
        "max_preview_rows": 20,
    }


@router.get("/imports/overview")
def imports_overview(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = scoped(db, ImportJob, request.state.org_id).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_type[row.import_type] = by_type.get(row.import_type, 0) + 1
    return {
        "jobs": len(rows),
        "validated": by_status.get("validated", 0),
        "needs_mapping": by_status.get("needs_mapping", 0),
        "imported": by_status.get("imported", 0),
        "failed": by_status.get("failed", 0),
        "records_total": sum(row.records_total or 0 for row in rows),
        "records_valid": sum(row.records_valid or 0 for row in rows),
        "records_imported": sum(row.records_imported or 0 for row in rows),
        "by_status": by_status,
        "by_type": by_type,
    }


@router.get("/imports/jobs")
def import_jobs(
    request: Request,
    status: str = "",
    import_type: str = "",
    client_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    skip, limit = _page(skip, limit, 1000)
    query = scoped(db, ImportJob, request.state.org_id)
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if any(item not in IMPORT_STATUSES for item in statuses):
            raise HTTPException(422, "Invalid import status")
        query = query.filter(ImportJob.status.in_(statuses))
    if import_type:
        if import_type not in REQUIRED_IMPORT_FIELDS:
            raise HTTPException(422, "Invalid import type")
        query = query.filter(ImportJob.import_type == import_type)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(ImportJob.client_id == client_id)
    clients = _client_names(db, request.state.org_id)
    return [_import_job_out(row, clients) for row in query.order_by(ImportJob.created_at.desc()).offset(skip).limit(limit).all()]


def _validate_import(import_type: str, mapping: dict[str, str], rows: list[dict[str, Any]]):
    required = REQUIRED_IMPORT_FIELDS.get(import_type, [])
    errors = []
    headers = set(rows[0].keys()) if rows else set()
    for field in required:
        source = mapping.get(field, field)
        if rows and source not in headers:
            errors.append({"field": field, "message": f"Missing mapped column '{source}'"})
        elif not rows and not source:
            errors.append({"field": field, "message": "Mapping is required"})
    valid_rows = 0
    for idx, row in enumerate(rows):
        missing = [field for field in required if not row.get(mapping.get(field, field))]
        if missing:
            errors.append({"row": idx + 1, "field": ",".join(missing), "message": "Required values are blank"})
        else:
            valid_rows += 1
    return errors, valid_rows


@router.post("/imports/jobs", status_code=201)
def create_import_job(payload: ImportJobRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.client_id:
        _client(db, request.state.org_id, payload.client_id)
    if payload.import_type not in REQUIRED_IMPORT_FIELDS:
        raise HTTPException(422, "Invalid import type")
    errors, valid_rows = _validate_import(payload.import_type, payload.mapping, payload.sample_rows)
    row = ImportJob(
        org_id=request.state.org_id, created_by=user.id, client_id=payload.client_id,
        import_type=payload.import_type, source_name=payload.source_name,
        mapping=payload.mapping, sample_rows=payload.sample_rows[:20],
        validation_errors=errors, records_total=len(payload.sample_rows),
        records_valid=valid_rows, status="validated" if not errors else "needs_mapping",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _import_job_out(row, _client_names(db, request.state.org_id))


@router.post("/imports/jobs/{job_id}/commit")
def commit_import_job(job_id: str, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, ImportJob, request.state.org_id).filter(ImportJob.id == job_id).first()
    if not row:
        raise HTTPException(404, "Import job not found")
    if row.validation_errors:
        raise HTTPException(400, "Resolve mapping errors before import")
    if row.status == "imported":
        raise HTTPException(409, "Import job already committed")
    row.status = "imported"
    row.records_imported = row.records_valid
    row.completed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _import_job_out(row, _client_names(db, request.state.org_id))


class SavedViewRequest(BaseModel):
    name: str
    view_type: str = "report"
    filters: dict[str, Any] = Field(default_factory=dict)
    columns: list[str] = Field(default_factory=list)
    is_shared: bool = False


@router.get("/reports/overview")
def reports_overview(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    today = date.today()
    clients = scoped(db, Client, request.state.org_id).all()
    tasks = scoped(db, PracticeTask, request.state.org_id)
    task_rows = tasks.all()
    invoices = scoped(db, PracticeInvoice, request.state.org_id).all()
    portal_pending = scoped(db, PortalRequest, request.state.org_id).filter(PortalRequest.status.in_(["requested", "in_progress"])).count()
    vault_expiring = scoped(db, CredentialVaultItem, request.state.org_id).filter(
        CredentialVaultItem.expires_on.isnot(None),
        CredentialVaultItem.expires_on <= today + timedelta(days=30),
    ).count()
    saved_count = scoped(db, SavedView, request.state.org_id).count()
    by_task_status: dict[str, int] = {}
    by_service_type: dict[str, int] = {}
    for row in task_rows:
        by_task_status[row.status] = by_task_status.get(row.status, 0) + 1
        by_service_type[row.service_type] = by_service_type.get(row.service_type, 0) + 1
    by_invoice_status: dict[str, int] = {}
    for row in invoices:
        by_invoice_status[row.status] = by_invoice_status.get(row.status, 0) + 1
    return {
        "clients": len(clients),
        "high_risk_clients": sum(1 for client in clients if client.health_score < 50),
        "open_tasks": tasks.filter(PracticeTask.status != "done").count(),
        "overdue_tasks": tasks.filter(PracticeTask.status != "done", PracticeTask.due_date < today).count(),
        "tasks_due_7_days": tasks.filter(PracticeTask.status != "done", PracticeTask.due_date <= today + timedelta(days=7)).count(),
        "outstanding": sum(max(_num(row.total) - _num(row.amount_paid), 0) for row in invoices if row.status != "paid"),
        "overdue_collections": sum(max(_num(row.total) - _num(row.amount_paid), 0) for row in invoices if row.status != "paid" and row.due_date < today),
        "portal_pending": portal_pending,
        "vault_expiring": vault_expiring,
        "saved_views": saved_count,
        "by_task_status": by_task_status,
        "by_service_type": by_service_type,
        "by_invoice_status": by_invoice_status,
    }


@router.get("/reports/saved-views")
def saved_views(
    request: Request,
    view_type: str = "",
    shared: str = "",
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    skip, limit = _page(skip, limit, 1000)
    query = scoped(db, SavedView, request.state.org_id).filter(
        (SavedView.user_id == user.id) | (SavedView.is_shared.is_(True))
    )
    if view_type:
        query = query.filter(SavedView.view_type == view_type)
    if shared:
        query = query.filter(SavedView.is_shared.is_(shared.lower() == "true"))
    rows = query.order_by(SavedView.created_at.desc()).offset(skip).limit(limit).all()
    users = _user_emails(db, request.state.org_id)
    return [{
        "id": str(row.id), "name": row.name, "view_type": row.view_type,
        "filters": row.filters, "columns": row.columns, "is_shared": row.is_shared,
        "user_id": str(row.user_id),
        "user_email": users.get(str(row.user_id), ""),
        "filter_count": len(row.filters or {}),
        "column_count": len(row.columns or []),
        "created_at": _datetime(row.created_at),
    } for row in rows]


@router.post("/reports/saved-views", status_code=201)
def create_saved_view(payload: SavedViewRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if not payload.name.strip():
        raise HTTPException(422, "Saved view name is required")
    row = SavedView(org_id=request.state.org_id, user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": str(row.id)}
