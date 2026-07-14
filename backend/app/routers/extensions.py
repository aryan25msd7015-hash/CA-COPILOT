"""Integrated APIs for the advanced automation modules."""
import io
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.engines.automation_engines import (
    ACTIVITY_BILLING_MAP,
    CERTIFICATE_TYPES, FILING_MATRIX, FILING_NAMES, analyze_debtors, analyze_stock,
    build_certificate_docx, build_dp_pdf, build_rows_xlsx, build_text_docx,
    check_rfp_eligibility, compute_deadline, compute_drawing_power,
    compute_lease_schedule, deadline_risk_score, extract_certificate_fields,
    extract_lease_data, generate_bid_proposal, generate_secretarial_document,
    get_fy, msme_violation_values, month_period, parse_udyam_certificate,
    validate_certificate_fields,
)
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.extensions import (
    BankFacility, CertificateRecord, DeadlineClientMap, DebtorItem,
    DrawingPowerStatement, FirmCredential, InventoryItem, LeaseRecord,
    MsmePaymentViolation, MsmeVendor, RfpBid, SecretarialDocument,
    TimesheetEntry, UserActivityLog,
)
from app.models.transaction import Transaction
from app.utils.deadline_sync import seed_client_applicability
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped

router = APIRouter()


def _page(skip: int, limit: int, max_limit: int = 5000):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > max_limit:
        raise HTTPException(422, f"limit must be between 1 and {max_limit}")
    return skip, limit


def _month_window(month: str):
    target = month or month_period()
    try:
        start = date.fromisoformat(target + "-01")
    except ValueError as exc:
        raise HTTPException(422, "Month must use YYYY-MM format") from exc
    end = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
    return start, end


def _client(db, org_id, client_id):
    row = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not row:
        raise HTTPException(404, "Client not found")
    return row


def _activity(db, request, user_id, activity_type, client_id=None, duration=300, details=None):
    db.add(UserActivityLog(
        org_id=request.state.org_id, user_id=user_id, client_id=client_id,
        activity_type=activity_type, duration_seconds=duration, details=details or {},
    ))


def _date(value):
    return value.isoformat() if value else None


def _num(value):
    return float(value or 0)


class CalendarUpdate(BaseModel):
    data_received: Optional[bool] = None
    data_source: Optional[str] = None
    status: Optional[str] = None


@router.post("/calendar/seed/{client_id}")
def seed_calendar(client_id: str, request: Request, period: str = "", db: Session = Depends(get_db),
                  _=Depends(require_role(["partner", "manager"]))):
    client = _client(db, request.state.org_id, client_id)
    target = period or month_period()
    count = seed_client_applicability(db, client, target)
    db.flush()
    _score_calendar_rows(db, request.state.org_id)
    db.commit()
    return {"created": count, "period": target}


def _score_calendar_rows(db, org_id):
    rows = scoped(db, DeadlineClientMap, org_id).filter(DeadlineClientMap.status == "pending").all()
    clients = {str(row.id): row for row in scoped(db, Client, org_id).all()}
    for row in rows:
        client = clients.get(str(row.client_id))
        row.risk_score = deadline_risk_score(
            row.deadline, row.data_received, row.late_count_last_12m,
            row.has_open_notice, client.health_score if client else 100,
        )
    return len(rows)


@router.post("/calendar/score")
def score_calendar(request: Request, db: Session = Depends(get_db),
                   _=Depends(require_role(["partner", "manager"]))):
    count = _score_calendar_rows(db, request.state.org_id)
    high_risk = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.status == "pending",
        DeadlineClientMap.risk_score >= 7,
    ).count()
    missing_data = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.status == "pending",
        DeadlineClientMap.data_received.is_(False),
    ).count()
    db.commit()
    return {"scored": count, "high_risk": high_risk, "missing_data": missing_data}


@router.get("/calendar/overview")
def calendar_overview(request: Request, days_ahead: int = 120, db: Session = Depends(get_db),
                      _=Depends(get_current_user)):
    end = date.today().fromordinal(date.today().toordinal() + days_ahead)
    rows = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.deadline >= date.today(), DeadlineClientMap.deadline <= end,
    ).order_by(DeadlineClientMap.deadline.asc(), DeadlineClientMap.risk_score.desc()).all()
    groups = {}
    for row in rows:
        key = (row.filing_type, row.period, row.deadline)
        group = groups.setdefault(key, {
            "filing_type": row.filing_type, "filing_name": row.filing_name,
            "period": row.period, "deadline": str(row.deadline), "total_pending": 0,
            "high_risk_count": 0, "data_missing": 0, "chronic_late": 0,
            "has_notice": 0, "max_risk": 0,
            "reminder_candidates": 0, "reminders_sent_total": 0,
        })
        group["total_pending"] += int(row.status == "pending")
        group["high_risk_count"] += int(row.status == "pending" and _num(row.risk_score) >= 7)
        group["data_missing"] += int(row.status == "pending" and not row.data_received)
        group["chronic_late"] += int(row.late_count_last_12m >= 2)
        group["has_notice"] += int(row.has_open_notice)
        group["reminder_candidates"] += int(row.status == "pending" and not row.data_received and row.reminders_sent < 3)
        group["reminders_sent_total"] += int(row.reminders_sent or 0)
        group["max_risk"] = max(group["max_risk"], _num(row.risk_score))
    result = []
    for group in groups.values():
        group["priority"] = "urgent" if group["max_risk"] >= 7 else "review" if group["max_risk"] >= 4 else "on_track"
        group["days_until_deadline"] = (date.fromisoformat(group["deadline"]) - date.today()).days
        result.append(group)
    return result


@router.get("/calendar/{filing_type}/{period}/clients")
def calendar_clients(filing_type: str, period: str, request: Request, db: Session = Depends(get_db),
                     _=Depends(get_current_user)):
    rows = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.filing_type == filing_type, DeadlineClientMap.period == period,
    ).order_by(DeadlineClientMap.risk_score.desc()).all()
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [{
        "id": str(row.id), "client_id": str(row.client_id),
        "client_name": clients.get(str(row.client_id)).name if clients.get(str(row.client_id)) else "",
        "gstin": clients.get(str(row.client_id)).gstin if clients.get(str(row.client_id)) else None,
        "health_score": clients.get(str(row.client_id)).health_score if clients.get(str(row.client_id)) else None,
        "risk_score": _num(row.risk_score), "data_received": row.data_received,
        "data_source": row.data_source, "late_count_last_12m": row.late_count_last_12m,
        "has_open_notice": row.has_open_notice, "reminders_sent": row.reminders_sent,
        "reminder_eligible": row.status == "pending" and not row.data_received and row.reminders_sent < 3,
        "last_reminder_at": _date(row.last_reminder_at),
        "status": row.status, "deadline": str(row.deadline),
    } for row in rows]


@router.patch("/calendar/items/{item_id}")
def update_calendar_item(item_id: str, payload: CalendarUpdate, request: Request, db: Session = Depends(get_db),
                         _=Depends(get_current_user)):
    row = scoped(db, DeadlineClientMap, request.state.org_id).filter(DeadlineClientMap.id == item_id).first()
    if not row:
        raise HTTPException(404, "Calendar item not found")
    for key, value in payload.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    if payload.data_received:
        row.data_received_at = datetime.now(timezone.utc)
    if payload.status == "filed":
        row.filed_at = datetime.now(timezone.utc)
    legacy = scoped(db, ComplianceDeadline, request.state.org_id).filter(
        ComplianceDeadline.client_id == row.client_id,
        ComplianceDeadline.filing_type == row.filing_type,
        ComplianceDeadline.period == row.period,
    ).first()
    if legacy and payload.status:
        legacy.status = payload.status
        legacy.filed_at = row.filed_at if payload.status == "filed" else legacy.filed_at
    client = _client(db, request.state.org_id, str(row.client_id))
    row.risk_score = deadline_risk_score(row.deadline, row.data_received, row.late_count_last_12m, row.has_open_notice, client.health_score)
    db.commit()
    return {"id": str(row.id), "risk_score": _num(row.risk_score)}


@router.post("/calendar/{filing_type}/{period}/bulk-remind")
def bulk_remind(filing_type: str, period: str, request: Request, db: Session = Depends(get_db),
                _=Depends(require_role(["partner", "manager"]))):
    from app.tasks.whatsapp_tasks import send_whatsapp_template
    rows = scoped(db, DeadlineClientMap, request.state.org_id).filter(
        DeadlineClientMap.filing_type == filing_type, DeadlineClientMap.period == period,
        DeadlineClientMap.data_received.is_(False), DeadlineClientMap.reminders_sent < 3,
        DeadlineClientMap.status == "pending",
    ).all()
    sent = blocked_no_consent = provider_skipped = 0
    for row in rows:
        client = _client(db, request.state.org_id, str(row.client_id))
        if not client.whatsapp_consent_at or not client.whatsapp_number:
            blocked_no_consent += 1
            continue
        try:
            send_whatsapp_template.delay(
                client.whatsapp_number, "data_request_reminder",
                [client.name, row.filing_name, row.deadline.strftime("%d %b"), row.filing_name],
                str(row.org_id), str(row.client_id),
            )
        except Exception:
            provider_skipped += 1
            continue
        row.reminders_sent += 1
        row.last_reminder_at = datetime.now(timezone.utc)
        sent += 1
    db.commit()
    return {
        "eligible": len(rows),
        "reminders_sent": sent,
        "blocked_no_consent": blocked_no_consent,
        "provider_skipped": provider_skipped,
        "skipped": len(rows) - sent,
    }


class MsmeVendorRequest(BaseModel):
    client_id: str
    vendor_name: str = ""
    vendor_gstin: Optional[str] = None
    udyam_reg_no: Optional[str] = None
    udyam_category: str = "micro"
    registered_at: Optional[date] = None
    certificate_text: Optional[str] = None


def _msme_vendor_out(row, clients=None):
    client = (clients or {}).get(str(row.client_id))
    return {
        "id": str(row.id), "client_id": str(row.client_id),
        "client_name": client.name if client else "",
        "vendor_name": row.vendor_name, "vendor_gstin": row.vendor_gstin,
        "udyam_reg_no": row.udyam_reg_no, "udyam_category": row.udyam_category,
        "registered_at": _date(row.registered_at), "verified_at": _date(row.verified_at),
        "is_verified": bool(row.verified_at), "has_udyam": bool(row.udyam_reg_no),
        "created_at": _date(row.created_at),
    }


def _msme_risk_bucket(days_overdue):
    days = int(days_overdue or 0)
    if days >= 90:
        return "severe"
    if days >= 45:
        return "high"
    if days > 0:
        return "medium"
    return "low"


@router.get("/msme/overview")
def msme_overview(request: Request, client_id: str = "", fy: str = "", db: Session = Depends(get_db),
                  _=Depends(get_current_user)):
    vendors_query = scoped(db, MsmeVendor, request.state.org_id)
    violations_query = scoped(db, MsmePaymentViolation, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        vendors_query = vendors_query.filter(MsmeVendor.client_id == client_id)
        violations_query = violations_query.filter(MsmePaymentViolation.client_id == client_id)
    if fy:
        violations_query = violations_query.filter(MsmePaymentViolation.fy == fy)

    vendors = vendors_query.all()
    violations = violations_query.all()
    open_rows = [row for row in violations if row.status == "open"]
    category_counts = {"micro": 0, "small": 0, "medium": 0}
    for vendor in vendors:
        if vendor.udyam_category in category_counts:
            category_counts[vendor.udyam_category] += 1
    return {
        "vendor_count": len(vendors),
        "verified_vendors": sum(1 for row in vendors if row.verified_at),
        "vendors_without_gstin": sum(1 for row in vendors if not row.vendor_gstin),
        "category_counts": category_counts,
        "open_violations": len(open_rows),
        "cleared_violations": sum(1 for row in violations if row.status == "cleared"),
        "affected_vendor_count": len({str(row.vendor_id) for row in open_rows}),
        "total_disallowance": round(sum(_num(row.disallowance_amount) for row in open_rows), 2),
        "total_interest": round(sum(_num(row.interest_amount) for row in open_rows), 2),
        "max_days_overdue": max([int(row.days_overdue or 0) for row in open_rows] or [0]),
    }


@router.get("/msme/vendors")
def msme_vendors(request: Request, client_id: str = "", udyam_category: str = "", verified: str = "",
                 has_gstin: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db),
                 _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, MsmeVendor, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(MsmeVendor.client_id == client_id)
    if udyam_category:
        query = query.filter(MsmeVendor.udyam_category == udyam_category)
    if verified == "true":
        query = query.filter(MsmeVendor.verified_at.isnot(None))
    elif verified == "false":
        query = query.filter(MsmeVendor.verified_at.is_(None))
    if has_gstin == "true":
        query = query.filter(MsmeVendor.vendor_gstin.isnot(None), MsmeVendor.vendor_gstin != "")
    elif has_gstin == "false":
        query = query.filter((MsmeVendor.vendor_gstin.is_(None)) | (MsmeVendor.vendor_gstin == ""))
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [_msme_vendor_out(row, clients) for row in query.order_by(MsmeVendor.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/msme/vendors", status_code=201)
def create_msme_vendor(payload: MsmeVendorRequest, request: Request, db: Session = Depends(get_db),
                       _=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    values = payload.model_dump(exclude={"certificate_text"})
    if payload.certificate_text:
        values.update(parse_udyam_certificate(payload.certificate_text))
    values["vendor_name"] = (values.get("vendor_name") or "").strip()
    values["vendor_gstin"] = (values.get("vendor_gstin") or "").strip().upper() or None
    values["udyam_reg_no"] = (values.get("udyam_reg_no") or "").strip().upper() or None
    values["udyam_category"] = (values.get("udyam_category") or "").strip().lower()
    if not values.get("vendor_name"):
        raise HTTPException(400, "Vendor name is required")
    if values.get("vendor_gstin") and len(values["vendor_gstin"]) != 15:
        raise HTTPException(422, "Vendor GSTIN must be 15 characters")
    if values.get("udyam_reg_no") and len(values["udyam_reg_no"]) > 30:
        raise HTTPException(422, "Udyam registration number must be 30 characters or fewer")
    if values.get("udyam_category") not in ("micro", "small", "medium"):
        raise HTTPException(422, "Invalid Udyam category")
    existing = scoped(db, MsmeVendor, request.state.org_id).filter(
        MsmeVendor.client_id == payload.client_id, MsmeVendor.vendor_gstin == values.get("vendor_gstin"),
    ).first() if values.get("vendor_gstin") else None
    row = existing or MsmeVendor(org_id=request.state.org_id, client_id=payload.client_id)
    for key, value in values.items():
        setattr(row, key, value)
    row.verified_at = datetime.now(timezone.utc)
    if not existing:
        db.add(row)
    db.commit()
    db.refresh(row)
    return _msme_vendor_out(row)


class MsmeScanRequest(BaseModel):
    client_id: str
    payment_dates: dict[str, date] = Field(default_factory=dict)


@router.post("/msme/scan")
def scan_msme(payload: MsmeScanRequest, request: Request, db: Session = Depends(get_db),
              user=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    vendors = scoped(db, MsmeVendor, request.state.org_id).filter(MsmeVendor.client_id == payload.client_id).all()
    created = 0
    updated = 0
    cleared = 0
    invoices_scanned = 0
    for vendor in vendors:
        if not vendor.vendor_gstin:
            continue
        invoices = scoped(db, Transaction, request.state.org_id).filter(
            Transaction.client_id == payload.client_id, Transaction.vendor_gstin == vendor.vendor_gstin,
            Transaction.date.isnot(None), Transaction.amount.isnot(None),
        ).all()
        for invoice in invoices:
            invoices_scanned += 1
            values = msme_violation_values(invoice.date, invoice.amount, payload.payment_dates.get(str(invoice.id)))
            row = scoped(db, MsmePaymentViolation, request.state.org_id).filter(
                MsmePaymentViolation.vendor_id == vendor.id, MsmePaymentViolation.invoice_id == invoice.id,
            ).first()
            if values["violated"]:
                if not row:
                    row = MsmePaymentViolation(
                        org_id=request.state.org_id, client_id=payload.client_id,
                        vendor_id=vendor.id, invoice_id=invoice.id, invoice_date=invoice.date,
                        invoice_amount=invoice.amount, fy=get_fy(invoice.date),
                    )
                    db.add(row)
                    created += 1
                else:
                    updated += 1
                for key in ("due_date", "days_overdue", "disallowance_amount", "interest_amount"):
                    setattr(row, key, values[key])
                row.payment_date = payload.payment_dates.get(str(invoice.id))
                row.status = "open"
            elif row:
                row.status = "cleared"
                row.payment_date = payload.payment_dates.get(str(invoice.id))
                cleared += 1
    _activity(db, request, user.id, "document_review", payload.client_id, 900, {"module": "msme"})
    db.commit()
    open_violations = scoped(db, MsmePaymentViolation, request.state.org_id).filter(
        MsmePaymentViolation.client_id == payload.client_id, MsmePaymentViolation.status == "open",
    ).count()
    return {
        "new_violations": created, "updated_violations": updated, "cleared_violations": cleared,
        "vendors_scanned": len([row for row in vendors if row.vendor_gstin]),
        "vendors_skipped": len([row for row in vendors if not row.vendor_gstin]),
        "invoices_scanned": invoices_scanned, "open_violations": open_violations,
    }


@router.get("/msme/violations")
def list_msme_violations(request: Request, client_id: str = "", fy: str = "", status: str = "",
                         skip: int = 0, limit: int = 200, db: Session = Depends(get_db),
                         _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, MsmePaymentViolation, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(MsmePaymentViolation.client_id == client_id)
    if fy:
        query = query.filter(MsmePaymentViolation.fy == fy)
    if status:
        query = query.filter(MsmePaymentViolation.status == status)
    vendors = {str(v.id): v for v in scoped(db, MsmeVendor, request.state.org_id).all()}
    return [{
        "id": str(row.id), "client_id": str(row.client_id), "invoice_id": str(row.invoice_id),
        "vendor_name": vendors.get(str(row.vendor_id)).vendor_name if vendors.get(str(row.vendor_id)) else "",
        "vendor_gstin": vendors.get(str(row.vendor_id)).vendor_gstin if vendors.get(str(row.vendor_id)) else "",
        "udyam_category": vendors.get(str(row.vendor_id)).udyam_category if vendors.get(str(row.vendor_id)) else "",
        "invoice_date": _date(row.invoice_date), "invoice_amount": _num(row.invoice_amount),
        "due_date": _date(row.due_date), "payment_date": _date(row.payment_date),
        "days_overdue": row.days_overdue, "disallowance_amount": _num(row.disallowance_amount),
        "interest_amount": _num(row.interest_amount), "fy": row.fy, "status": row.status,
        "risk_bucket": _msme_risk_bucket(row.days_overdue),
    } for row in query.order_by(MsmePaymentViolation.days_overdue.desc()).offset(skip).limit(limit).all()]


@router.get("/msme/clause-22/{client_id}/{fy}")
def clause_22(client_id: str, fy: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _client(db, request.state.org_id, client_id)
    rows = scoped(db, MsmePaymentViolation, request.state.org_id).filter(
        MsmePaymentViolation.client_id == client_id, MsmePaymentViolation.fy == fy,
        MsmePaymentViolation.status == "open",
    ).all()
    vendors = {str(row.id): row for row in scoped(db, MsmeVendor, request.state.org_id).filter(MsmeVendor.client_id == client_id).all()}
    category_breakdown = {}
    for row in rows:
        vendor = vendors.get(str(row.vendor_id))
        category = vendor.udyam_category if vendor else "unknown"
        bucket = category_breakdown.setdefault(category, {"count": 0, "disallowance": 0, "interest": 0})
        bucket["count"] += 1
        bucket["disallowance"] = round(bucket["disallowance"] + _num(row.disallowance_amount), 2)
        bucket["interest"] = round(bucket["interest"] + _num(row.interest_amount), 2)
    return {
        "clause": "22 - Section 43B(h)", "fy": fy,
        "total_disallowance": round(sum(_num(row.disallowance_amount) for row in rows), 2),
        "total_interest": round(sum(_num(row.interest_amount) for row in rows), 2),
        "vendor_count": len({str(row.vendor_id) for row in rows}), "violation_count": len(rows),
        "max_days_overdue": max([int(row.days_overdue or 0) for row in rows] or [0]),
        "category_breakdown": category_breakdown,
        "top_rows": [{
            "vendor_name": vendors.get(str(row.vendor_id)).vendor_name if vendors.get(str(row.vendor_id)) else "",
            "days_overdue": row.days_overdue, "disallowance_amount": _num(row.disallowance_amount),
            "interest_amount": _num(row.interest_amount),
        } for row in sorted(rows, key=lambda item: item.days_overdue or 0, reverse=True)[:10]],
    }


@router.get("/msme/export/{client_id}/{fy}")
def export_msme(client_id: str, fy: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = list_msme_violations(request, client_id=client_id, fy=fy, skip=0, limit=5000, db=db, _=_)
    data = build_rows_xlsx("Clause 22", ["Vendor", "Category", "Invoice date", "Amount", "Due date", "Days overdue", "Disallowance", "Interest", "Status"], [
        [r["vendor_name"], r["udyam_category"], r["invoice_date"], r["invoice_amount"], r["due_date"], r["days_overdue"], r["disallowance_amount"], r["interest_amount"], r["status"]] for r in rows
    ])
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="msme-clause-22-{fy}.xlsx"'})


class FacilityRequest(BaseModel):
    client_id: str
    bank_name: str
    facility_type: str = "CC"
    sanctioned_limit: float
    margin_rules: dict[str, Any] = Field(default_factory=lambda: {"stock_margin": 0.25, "debtor_margin": 0.25, "stock_age_cutoff_days": 180, "debtor_age_cutoff_days": 90, "creditor_deduction": True})


def _validate_period(period: str):
    try:
        _month_window(period)
    except HTTPException as exc:
        raise HTTPException(422, "Period must use YYYY-MM format") from exc


def _facility_out(row, latest_statement=None):
    utilization = None
    if latest_statement and _num(row.sanctioned_limit) > 0:
        utilization = round(_num(latest_statement.drawing_power) / _num(row.sanctioned_limit) * 100, 1)
    return {
        "id": str(row.id), "client_id": str(row.client_id),
        "bank_name": row.bank_name, "facility_type": row.facility_type,
        "sanctioned_limit": _num(row.sanctioned_limit), "margin_rules": row.margin_rules,
        "created_at": _date(row.created_at),
        "latest_period": latest_statement.period if latest_statement else None,
        "latest_drawing_power": _num(latest_statement.drawing_power) if latest_statement else 0,
        "utilization_pct": utilization,
    }


def _dp_statement_out(row, facilities=None):
    facility = (facilities or {}).get(str(row.facility_id))
    sanctioned_limit = _num(facility.sanctioned_limit) if facility else 0
    utilization = round(_num(row.drawing_power) / sanctioned_limit * 100, 1) if sanctioned_limit else 0
    details = row.details or {}
    return {
        "id": str(row.id), "client_id": str(row.client_id), "facility_id": str(row.facility_id),
        "bank_name": facility.bank_name if facility else "", "facility_type": facility.facility_type if facility else "",
        "sanctioned_limit": sanctioned_limit, "period": row.period,
        "gross_stock": _num(row.gross_stock), "eligible_stock": _num(row.eligible_stock),
        "gross_debtors": _num(row.gross_debtors), "eligible_debtors": _num(row.eligible_debtors),
        "creditors": _num(row.creditors), "drawing_power": _num(row.drawing_power),
        "utilization_pct": utilization, "created_at": _date(row.created_at),
        "stock_dp": _num((details.get("stock") or {}).get("stock_dp")),
        "debtor_dp": _num((details.get("debtors") or {}).get("debtor_dp")),
        "ineligible_stock": _num((details.get("stock") or {}).get("ineligible_value")),
        "ineligible_debtors": _num((details.get("debtors") or {}).get("ineligible_value")),
        "at_risk_debtors": int((details.get("debtors") or {}).get("at_risk_count") or 0),
        "details": details,
    }


@router.get("/drawing-power/overview")
def drawing_power_overview(request: Request, client_id: str = "", period: str = "",
                           db: Session = Depends(get_db), _=Depends(get_current_user)):
    if period:
        _validate_period(period)
    facilities_query = scoped(db, BankFacility, request.state.org_id)
    statements_query = scoped(db, DrawingPowerStatement, request.state.org_id)
    inventory_query = scoped(db, InventoryItem, request.state.org_id)
    debtors_query = scoped(db, DebtorItem, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        facilities_query = facilities_query.filter(BankFacility.client_id == client_id)
        statements_query = statements_query.filter(DrawingPowerStatement.client_id == client_id)
        inventory_query = inventory_query.filter(InventoryItem.client_id == client_id)
        debtors_query = debtors_query.filter(DebtorItem.client_id == client_id)
    if period:
        statements_query = statements_query.filter(DrawingPowerStatement.period == period)
        inventory_query = inventory_query.filter(InventoryItem.period == period)
        debtors_query = debtors_query.filter(DebtorItem.period == period)
    statements = statements_query.all()
    sanctioned = sum(_num(row.sanctioned_limit) for row in facilities_query.all())
    drawing_power = sum(_num(row.drawing_power) for row in statements)
    return {
        "facility_count": facilities_query.count(),
        "statement_count": len(statements),
        "inventory_items": inventory_query.count(),
        "debtor_items": debtors_query.count(),
        "sanctioned_limit": round(sanctioned, 2),
        "drawing_power": round(drawing_power, 2),
        "available_headroom": round(max(sanctioned - drawing_power, 0), 2),
        "average_utilization_pct": round(drawing_power / sanctioned * 100, 1) if sanctioned else 0,
        "ineligible_stock": round(sum(_num((row.details or {}).get("stock", {}).get("ineligible_value")) for row in statements), 2),
        "ineligible_debtors": round(sum(_num((row.details or {}).get("debtors", {}).get("ineligible_value")) for row in statements), 2),
        "at_risk_debtors": sum(int((row.details or {}).get("debtors", {}).get("at_risk_count") or 0) for row in statements),
    }


@router.get("/drawing-power/facilities")
def facilities(request: Request, client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, BankFacility, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(BankFacility.client_id == client_id)
    rows = query.offset(skip).limit(limit).all()
    latest = {}
    for statement in scoped(db, DrawingPowerStatement, request.state.org_id).order_by(DrawingPowerStatement.created_at.desc()).all():
        latest.setdefault(str(statement.facility_id), statement)
    return [_facility_out(row, latest.get(str(row.id))) for row in rows]


@router.post("/drawing-power/facilities", status_code=201)
def create_facility(payload: FacilityRequest, request: Request, db: Session = Depends(get_db),
                    _=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    payload.bank_name = payload.bank_name.strip()
    payload.facility_type = payload.facility_type.strip().upper()
    if not payload.bank_name:
        raise HTTPException(400, "Bank name is required")
    if payload.facility_type not in ("CC", "OD", "WCDL", "FBP", "PCFC"):
        raise HTTPException(422, "Unsupported facility type")
    if payload.sanctioned_limit <= 0:
        raise HTTPException(422, "Sanctioned limit must be positive")
    for key in ("stock_margin", "debtor_margin"):
        margin = float(payload.margin_rules.get(key, 0))
        if margin < 0 or margin > 1:
            raise HTTPException(422, f"{key} must be between 0 and 1")
    row = BankFacility(org_id=request.state.org_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _facility_out(row)


class LedgerRequest(BaseModel):
    client_id: str
    period: str
    inventory: list[dict[str, Any]] = Field(default_factory=list)
    debtors: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/drawing-power/ledger")
def replace_dp_ledger(payload: LedgerRequest, request: Request, db: Session = Depends(get_db),
                      _=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    _validate_period(payload.period)
    rejected = []
    scoped(db, InventoryItem, request.state.org_id).filter(InventoryItem.client_id == payload.client_id, InventoryItem.period == payload.period).delete(synchronize_session=False)
    scoped(db, DebtorItem, request.state.org_id).filter(DebtorItem.client_id == payload.client_id, DebtorItem.period == payload.period).delete(synchronize_session=False)
    inventory_count = debtor_count = 0
    for index, row in enumerate(payload.inventory):
        try:
            value = float(row.get("stock_value") or 0)
            if not row.get("sku") or value < 0:
                raise ValueError("SKU and non-negative stock value are required")
            db.add(InventoryItem(org_id=request.state.org_id, client_id=payload.client_id, period=payload.period, **row))
            inventory_count += 1
        except Exception as exc:
            rejected.append({"type": "inventory", "index": index, "reason": str(exc)})
    for index, row in enumerate(payload.debtors):
        try:
            outstanding = float(row.get("outstanding") or 0)
            if not row.get("debtor_name") or not row.get("invoice_date") or outstanding < 0:
                raise ValueError("Debtor name, invoice date, and non-negative outstanding are required")
            db.add(DebtorItem(org_id=request.state.org_id, client_id=payload.client_id, period=payload.period, **row))
            debtor_count += 1
        except Exception as exc:
            rejected.append({"type": "debtor", "index": index, "reason": str(exc)})
    db.commit()
    return {"inventory_count": inventory_count, "debtor_count": debtor_count, "rejected_count": len(rejected), "rejected": rejected[:20]}


class DrawingPowerRun(BaseModel):
    facility_id: str
    period: str
    creditors: float = 0


@router.post("/drawing-power/compute")
def run_drawing_power(payload: DrawingPowerRun, request: Request, db: Session = Depends(get_db),
                      user=Depends(require_role(["partner", "manager"]))):
    facility = scoped(db, BankFacility, request.state.org_id).filter(BankFacility.id == payload.facility_id).first()
    if not facility:
        raise HTTPException(404, "Bank facility not found")
    _validate_period(payload.period)
    if payload.creditors < 0:
        raise HTTPException(422, "Creditors cannot be negative")
    inventory = scoped(db, InventoryItem, request.state.org_id).filter(InventoryItem.client_id == facility.client_id, InventoryItem.period == payload.period).all()
    debtors = scoped(db, DebtorItem, request.state.org_id).filter(DebtorItem.client_id == facility.client_id, DebtorItem.period == payload.period).all()
    if not inventory and not debtors:
        raise HTTPException(422, "Import inventory or debtor ledger before computing drawing power")
    stock = analyze_stock(inventory, facility.margin_rules or {})
    debtor_data = analyze_debtors(debtors, facility.margin_rules or {})
    dp = compute_drawing_power(stock, debtor_data, payload.creditors, facility.margin_rules or {}, facility.sanctioned_limit)
    row = scoped(db, DrawingPowerStatement, request.state.org_id).filter(DrawingPowerStatement.facility_id == facility.id, DrawingPowerStatement.period == payload.period).first()
    if not row:
        row = DrawingPowerStatement(org_id=request.state.org_id, client_id=facility.client_id, facility_id=facility.id, period=payload.period)
        db.add(row)
    row.gross_stock, row.eligible_stock = stock["gross_stock"], stock["eligible_stock"]
    row.gross_debtors, row.eligible_debtors = debtor_data["gross_debtors"], debtor_data["eligible_debtors"]
    row.creditors, row.drawing_power, row.details = payload.creditors, dp, {
        "stock": stock, "debtors": debtor_data,
        "rules": facility.margin_rules or {}, "sanctioned_limit": _num(facility.sanctioned_limit),
        "creditor_deduction": bool((facility.margin_rules or {}).get("creditor_deduction", True)),
    }
    _activity(db, request, user.id, "document_review", str(facility.client_id), 1200, {"module": "drawing_power"})
    db.commit()
    db.refresh(row)
    return _dp_statement_out(row, {str(facility.id): facility})


@router.get("/drawing-power/statements")
def drawing_power_statements(request: Request, client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, DrawingPowerStatement, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(DrawingPowerStatement.client_id == client_id)
    rows = query.order_by(DrawingPowerStatement.created_at.desc()).offset(skip).limit(limit).all()
    facilities_map = {str(row.id): row for row in scoped(db, BankFacility, request.state.org_id).all()}
    return [_dp_statement_out(row, facilities_map) for row in rows]


@router.get("/drawing-power/export/{statement_id}.{format}")
def export_drawing_power(statement_id: str, format: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, DrawingPowerStatement, request.state.org_id).filter(DrawingPowerStatement.id == statement_id).first()
    if not row:
        raise HTTPException(404, "Statement not found")
    if format not in ("pdf", "xlsx"):
        raise HTTPException(422, "Format must be pdf or xlsx")
    facility = scoped(db, BankFacility, request.state.org_id).filter(BankFacility.id == row.facility_id).first()
    client = _client(db, request.state.org_id, str(row.client_id))
    if format == "pdf":
        data, media = build_dp_pdf(client.name, facility.bank_name, row), "application/pdf"
    else:
        details = row.details or {}
        data, media = build_rows_xlsx("Drawing Power", ["Particular", "Amount"], [
            ["Bank", facility.bank_name if facility else ""],
            ["Facility type", facility.facility_type if facility else ""],
            ["Sanctioned limit", _num(facility.sanctioned_limit) if facility else 0],
            ["Gross stock", _num(row.gross_stock)], ["Eligible stock", _num(row.eligible_stock)],
            ["Stock DP", _num((details.get("stock") or {}).get("stock_dp"))],
            ["Gross debtors", _num(row.gross_debtors)], ["Eligible debtors", _num(row.eligible_debtors)],
            ["Debtor DP", _num((details.get("debtors") or {}).get("debtor_dp"))],
            ["Creditors", _num(row.creditors)], ["Drawing power", _num(row.drawing_power)],
        ]), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="drawing-power-{row.period}.{format}"'})


class CertificateRequest(BaseModel):
    client_id: str
    cert_type: str
    source_text: str = ""
    fields: dict[str, Any] = Field(default_factory=dict)
    reference_values: dict[str, float] = Field(default_factory=dict)


def _certificate_completeness(fields, cert_type):
    required = CERTIFICATE_TYPES.get(cert_type, ("", []))[1]
    if not required:
        return 0
    present = [field for field in required if fields.get(field) not in (None, "")]
    return round(len(present) / len(required) * 100, 1)


def _certificate_out(row, clients=None):
    validation = row.validation or {}
    fields = row.fields or {}
    client = (clients or {}).get(str(row.client_id))
    return {
        "id": str(row.id), "client_id": str(row.client_id),
        "client_name": client.name if client else "",
        "cert_type": row.cert_type, "title": row.title, "fields": fields,
        "validation": validation, "status": row.status, "created_at": _date(row.created_at),
        "missing_count": len(validation.get("missing_fields") or []),
        "issue_count": len(validation.get("issues") or []),
        "completeness_pct": _certificate_completeness(fields, row.cert_type),
        "export_ready": row.status == "ready" and bool(validation.get("valid")),
    }


@router.get("/certificates/types")
def certificate_types(_=Depends(get_current_user)):
    return [{"id": key, "title": value[0], "fields": value[1], "field_count": len(value[1])} for key, value in CERTIFICATE_TYPES.items()]


@router.get("/certificates/overview")
def certificate_overview(request: Request, client_id: str = "", db: Session = Depends(get_db),
                         _=Depends(get_current_user)):
    query = scoped(db, CertificateRecord, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(CertificateRecord.client_id == client_id)
    rows = query.all()
    status_counts = {}
    type_counts = {}
    missing_total = issue_total = 0
    for row in rows:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        type_counts[row.cert_type] = type_counts.get(row.cert_type, 0) + 1
        validation = row.validation or {}
        missing_total += len(validation.get("missing_fields") or [])
        issue_total += len(validation.get("issues") or [])
    ready = status_counts.get("ready", 0)
    return {
        "total": len(rows), "ready": ready,
        "review_required": status_counts.get("review_required", 0),
        "draft": status_counts.get("draft", 0),
        "approved": status_counts.get("approved", 0),
        "missing_fields": missing_total, "validation_issues": issue_total,
        "ready_rate_pct": round(ready / max(len(rows), 1) * 100, 1),
        "status_counts": status_counts, "type_counts": type_counts,
    }


@router.get("/certificates")
def certificates(request: Request, client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, CertificateRecord, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(CertificateRecord.client_id == client_id)
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [_certificate_out(row, clients) for row in query.order_by(CertificateRecord.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/certificates", status_code=201)
def create_certificate(payload: CertificateRequest, request: Request, db: Session = Depends(get_db),
                       user=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    if payload.cert_type not in CERTIFICATE_TYPES:
        raise HTTPException(400, "Unsupported certificate type")
    try:
        extracted = extract_certificate_fields(payload.source_text, payload.cert_type) if payload.source_text else {field: None for field in CERTIFICATE_TYPES[payload.cert_type][1]}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    extracted.update(payload.fields)
    validation = validate_certificate_fields(extracted, payload.reference_values)
    row = CertificateRecord(
        org_id=request.state.org_id, client_id=payload.client_id, cert_type=payload.cert_type,
        title=CERTIFICATE_TYPES[payload.cert_type][0], fields=extracted, validation=validation,
        status="ready" if validation["valid"] else "review_required", created_by=user.id,
    )
    db.add(row)
    _activity(db, request, user.id, "certificate_gen", payload.client_id, 600, {"cert_type": payload.cert_type})
    db.commit()
    db.refresh(row)
    return _certificate_out(row)


class CertificateUpdate(BaseModel):
    fields: dict[str, Any] = Field(default_factory=dict)
    reference_values: dict[str, float] = Field(default_factory=dict)
    status: Optional[str] = None


@router.patch("/certificates/{certificate_id}")
def update_certificate(certificate_id: str, payload: CertificateUpdate, request: Request, db: Session = Depends(get_db),
                       _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, CertificateRecord, request.state.org_id).filter(CertificateRecord.id == certificate_id).first()
    if not row:
        raise HTTPException(404, "Certificate not found")
    if payload.status and payload.status not in ("draft", "review_required", "ready", "approved"):
        raise HTTPException(422, "Invalid certificate status")
    fields = {**(row.fields or {}), **payload.fields}
    row.fields = fields
    row.validation = validate_certificate_fields(fields, payload.reference_values)
    if payload.status == "approved" and not row.validation["valid"]:
        raise HTTPException(422, "Certificate cannot be approved while validation issues remain")
    row.status = payload.status if payload.status in ("draft", "approved") else ("ready" if row.validation["valid"] else "review_required")
    db.commit()
    return _certificate_out(row)


@router.get("/certificates/{certificate_id}/export")
def export_certificate(certificate_id: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, CertificateRecord, request.state.org_id).filter(CertificateRecord.id == certificate_id).first()
    if not row:
        raise HTTPException(404, "Certificate not found")
    client = _client(db, request.state.org_id, str(row.client_id))
    data = build_certificate_docx(row.title, client, row.fields or {}, row.validation or {})
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="{row.cert_type}-certificate.docx"'})


class SecretarialRequest(BaseModel):
    client_id: str
    doc_type: str = "board_minutes"
    transcript: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class SecretarialUpdate(BaseModel):
    status: Optional[str] = None
    generated_text: Optional[str] = None
    structured_data: dict[str, Any] = Field(default_factory=dict)


SECRETARIAL_TYPES = {
    "board_minutes": "Board minutes + MGT-14",
    "agm_notice": "AGM notice",
    "mgt7": "MGT-7 data sheet",
    "aoc4": "AOC-4 data sheet",
    "mgt14": "MGT-14 filing data",
}


def _secretarial_flags(row):
    data = row.structured_data or {}
    flags = []
    if not data.get("meeting_date"):
        flags.append("missing_meeting_date")
    if not data.get("venue"):
        flags.append("missing_venue")
    if row.doc_type in ("board_minutes", "mgt14") and not data.get("resolutions"):
        flags.append("no_resolutions")
    if row.doc_type in ("board_minutes", "mgt14") and not row.generated_xml:
        flags.append("mgt14_xml_missing")
    return flags


def _secretarial_out(row, clients=None):
    data = row.structured_data or {}
    client = (clients or {}).get(str(row.client_id))
    flags = _secretarial_flags(row)
    resolutions = data.get("resolutions") or []
    return {
        "id": str(row.id), "client_id": str(row.client_id),
        "client_name": client.name if client else "",
        "doc_type": row.doc_type, "doc_title": SECRETARIAL_TYPES.get(row.doc_type, row.doc_type),
        "structured_data": data, "generated_text": row.generated_text,
        "has_xml": bool(row.generated_xml), "status": row.status, "created_at": _date(row.created_at),
        "meeting_date": data.get("meeting_date"), "meeting_type": data.get("meeting_type"),
        "resolution_count": len(resolutions), "director_count": len(data.get("directors_present") or []),
        "compliance_flags": flags, "review_ready": not flags,
        "word_count": len((row.generated_text or "").split()),
    }


@router.get("/secretarial/types")
def secretarial_types(_=Depends(get_current_user)):
    return [{"id": key, "title": title, "xml_supported": key in ("board_minutes", "mgt14")} for key, title in SECRETARIAL_TYPES.items()]


@router.get("/secretarial/overview")
def secretarial_overview(request: Request, client_id: str = "", db: Session = Depends(get_db),
                         _=Depends(get_current_user)):
    query = scoped(db, SecretarialDocument, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(SecretarialDocument.client_id == client_id)
    rows = query.all()
    status_counts = {}
    type_counts = {}
    xml_count = flagged_count = 0
    for row in rows:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
        type_counts[row.doc_type] = type_counts.get(row.doc_type, 0) + 1
        xml_count += int(bool(row.generated_xml))
        flagged_count += int(bool(_secretarial_flags(row)))
    return {
        "total": len(rows), "draft": status_counts.get("draft", 0),
        "approved": status_counts.get("approved", 0), "review_required": status_counts.get("review_required", 0),
        "xml_ready": xml_count, "flagged": flagged_count,
        "approval_rate_pct": round(status_counts.get("approved", 0) / max(len(rows), 1) * 100, 1),
        "status_counts": status_counts, "type_counts": type_counts,
    }


@router.get("/secretarial")
def secretarial_list(request: Request, client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, SecretarialDocument, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(SecretarialDocument.client_id == client_id)
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [_secretarial_out(row, clients) for row in query.order_by(SecretarialDocument.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/secretarial", status_code=201)
def create_secretarial(payload: SecretarialRequest, request: Request, db: Session = Depends(get_db),
                       user=Depends(require_role(["partner", "manager"]))):
    client = _client(db, request.state.org_id, payload.client_id)
    if payload.doc_type not in SECRETARIAL_TYPES:
        raise HTTPException(422, "Unsupported secretarial document type")
    if not payload.transcript.strip() and payload.doc_type not in ("mgt7", "aoc4"):
        raise HTTPException(400, "Transcript is required for minutes and notices")
    structured, generated, xml = generate_secretarial_document(payload.doc_type, client, payload.transcript, payload.data)
    row = SecretarialDocument(org_id=request.state.org_id, client_id=payload.client_id, doc_type=payload.doc_type, transcript=payload.transcript, structured_data=structured, generated_text=generated, generated_xml=xml, created_by=user.id)
    row.status = "review_required" if _secretarial_flags(row) else "draft"
    db.add(row)
    _activity(db, request, user.id, "secretarial_gen", payload.client_id, 900, {"doc_type": payload.doc_type})
    db.commit()
    db.refresh(row)
    return _secretarial_out(row)


@router.patch("/secretarial/{document_id}")
def update_secretarial(document_id: str, payload: SecretarialUpdate, request: Request, db: Session = Depends(get_db),
                       _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, SecretarialDocument, request.state.org_id).filter(SecretarialDocument.id == document_id).first()
    if not row:
        raise HTTPException(404, "Secretarial document not found")
    if payload.generated_text is not None:
        row.generated_text = payload.generated_text
    if payload.structured_data:
        row.structured_data = {**(row.structured_data or {}), **payload.structured_data}
    if payload.status:
        if payload.status not in ("draft", "review_required", "approved"):
            raise HTTPException(422, "Invalid secretarial document status")
        if payload.status == "approved" and _secretarial_flags(row):
            raise HTTPException(422, "Document cannot be approved while compliance flags remain")
        row.status = payload.status
    elif _secretarial_flags(row):
        row.status = "review_required"
    db.commit()
    return _secretarial_out(row)


@router.get("/secretarial/{document_id}/export/{format}")
def export_secretarial(document_id: str, format: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, SecretarialDocument, request.state.org_id).filter(SecretarialDocument.id == document_id).first()
    if not row:
        raise HTTPException(404, "Secretarial document not found")
    if format not in ("docx", "xml"):
        raise HTTPException(422, "Format must be docx or xml")
    if format == "xml":
        if not row.generated_xml:
            raise HTTPException(400, "XML is only available for MGT-14 compatible documents")
        data, media = row.generated_xml.encode(), "application/xml"
    else:
        data, media = build_text_docx(row.doc_type.replace("_", " ").title(), row.generated_text), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return StreamingResponse(io.BytesIO(data), media_type=media, headers={"Content-Disposition": f'attachment; filename="{row.doc_type}.{format}"'})


class LeaseRequest(BaseModel):
    client_id: str
    name: str
    source_text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


def _lease_flags(extracted, schedule, ibr_assumed):
    flags = []
    if not extracted.get("commencement_date"):
        flags.append("missing_commencement_date")
    if int(extracted.get("lease_term_months") or 0) <= 0:
        flags.append("invalid_lease_term")
    if float(extracted.get("base_rent_monthly") or 0) <= 0 and not extracted.get("lease_payments_schedule"):
        flags.append("missing_rent")
    if ibr_assumed:
        flags.append("ibr_assumed")
    if not schedule:
        flags.append("empty_schedule")
    return flags


def _lease_summary(row):
    extracted = row.extracted_data or {}
    schedule = row.schedule or []
    total_payments = round(sum(_num(item.get("payment")) for item in schedule), 2)
    total_interest = round(sum(_num(item.get("interest_expense")) for item in schedule), 2)
    liability = _num(extracted.get("initial_lease_liability"))
    rou_asset = _num(extracted.get("initial_rou_asset"))
    return {
        "initial_lease_liability": liability,
        "initial_rou_asset": rou_asset,
        "months": len(schedule),
        "total_payments": total_payments,
        "total_interest": total_interest,
        "monthly_rent": _num(extracted.get("base_rent_monthly")),
        "ibr_pct": _num(extracted.get("incremental_borrowing_rate_pct")),
        "commencement_date": extracted.get("commencement_date"),
        "rent_free_months": int(extracted.get("rent_free_period_months") or 0),
        "ending_liability": _num(schedule[-1].get("lease_liability")) if schedule else 0,
    }


def _lease_out(row, clients=None):
    client = (clients or {}).get(str(row.client_id))
    summary = _lease_summary(row)
    flags = _lease_flags(row.extracted_data or {}, row.schedule or [], row.ibr_assumed)
    return {
        "id": str(row.id), "client_id": str(row.client_id),
        "client_name": client.name if client else "",
        "name": row.name, "extracted_data": row.extracted_data, "schedule": row.schedule,
        "summary": summary, "ibr_assumed": row.ibr_assumed, "verified": row.verified,
        "review_flags": flags, "review_ready": not flags or flags == ["ibr_assumed"],
        "created_at": _date(row.created_at),
    }


def _compute_lease_or_422(extracted):
    try:
        if int(extracted.get("lease_term_months") or 0) <= 0:
            raise ValueError("Lease term must be positive")
        if float(extracted.get("incremental_borrowing_rate_pct") or 0) < 0:
            raise ValueError("IBR cannot be negative")
        return compute_lease_schedule(extracted)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/leases/overview")
def leases_overview(request: Request, client_id: str = "", db: Session = Depends(get_db),
                    _=Depends(get_current_user)):
    query = scoped(db, LeaseRecord, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(LeaseRecord.client_id == client_id)
    rows = query.all()
    liability = sum(_num((row.extracted_data or {}).get("initial_lease_liability")) for row in rows)
    rou_asset = sum(_num((row.extracted_data or {}).get("initial_rou_asset")) for row in rows)
    return {
        "total": len(rows), "verified": sum(1 for row in rows if row.verified),
        "pending_review": sum(1 for row in rows if not row.verified),
        "ibr_assumed": sum(1 for row in rows if row.ibr_assumed),
        "total_liability": round(liability, 2), "total_rou_asset": round(rou_asset, 2),
        "total_payments": round(sum(_lease_summary(row)["total_payments"] for row in rows), 2),
        "total_interest": round(sum(_lease_summary(row)["total_interest"] for row in rows), 2),
        "average_term_months": round(sum(len(row.schedule or []) for row in rows) / max(len(rows), 1), 1),
    }


@router.get("/leases")
def leases(request: Request, client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, LeaseRecord, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(LeaseRecord.client_id == client_id)
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [_lease_out(row, clients) for row in query.order_by(LeaseRecord.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/leases", status_code=201)
def create_lease(payload: LeaseRequest, request: Request, db: Session = Depends(get_db),
                 user=Depends(require_role(["partner", "manager"]))):
    _client(db, request.state.org_id, payload.client_id)
    payload.name = payload.name.strip()
    if not payload.name:
        raise HTTPException(400, "Lease name is required")
    extracted = extract_lease_data(payload.source_text, payload.data)
    computed = _compute_lease_or_422(extracted)
    extracted.update({key: value for key, value in computed.items() if key != "schedule"})
    row = LeaseRecord(org_id=request.state.org_id, client_id=payload.client_id, name=payload.name, source_text=payload.source_text, extracted_data=extracted, schedule=computed["schedule"], ibr_assumed=not bool(payload.data.get("incremental_borrowing_rate_pct")))
    db.add(row)
    _activity(db, request, user.id, "lease_schedule", payload.client_id, 1200, {"name": payload.name})
    db.commit()
    db.refresh(row)
    return _lease_out(row)


class LeaseUpdate(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)
    verified: Optional[bool] = None


@router.patch("/leases/{lease_id}")
def update_lease(lease_id: str, payload: LeaseUpdate, request: Request, db: Session = Depends(get_db),
                 _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, LeaseRecord, request.state.org_id).filter(LeaseRecord.id == lease_id).first()
    if not row:
        raise HTTPException(404, "Lease not found")
    extracted = extract_lease_data(row.source_text or "", {**(row.extracted_data or {}), **payload.data})
    computed = _compute_lease_or_422(extracted)
    extracted.update({key: value for key, value in computed.items() if key != "schedule"})
    row.extracted_data, row.schedule = extracted, computed["schedule"]
    if payload.verified is not None:
        row.verified = payload.verified
    if "incremental_borrowing_rate_pct" in payload.data:
        row.ibr_assumed = False
    db.commit()
    return _lease_out(row)


@router.get("/leases/{lease_id}/export")
def export_lease(lease_id: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, LeaseRecord, request.state.org_id).filter(LeaseRecord.id == lease_id).first()
    if not row:
        raise HTTPException(404, "Lease not found")
    summary = _lease_summary(row)
    rows = [
        ["Lease", row.name, "", "", "", ""],
        ["Commencement", summary["commencement_date"], "", "", "", ""],
        ["IBR %", summary["ibr_pct"], "", "", "", ""],
        ["Initial liability", summary["initial_lease_liability"], "", "", "", ""],
        ["", "", "", "", "", ""],
    ] + [[item["month"], item["payment"], item["interest_expense"], item["principal"], item["lease_liability"], item["rou_asset"]] for item in row.schedule]
    data = build_rows_xlsx("Ind AS 116 Schedule", ["Month", "Payment", "Interest expense", "Principal", "Lease liability", "ROU asset"], rows)
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="lease-schedule-{lease_id}.xlsx"'})


class CredentialRequest(BaseModel):
    firm_name: str
    icai_regn_no: str = ""
    founding_year: int = date.today().year
    hq_city: str = ""
    hq_state: str = ""
    partners: list[dict[str, Any]] = Field(default_factory=list)
    article_clerks: int = 0
    total_staff: int = 0
    gross_fee_receipts_fy1: float = 0
    gross_fee_receipts_fy2: float = 0
    gross_fee_receipts_fy3: float = 0
    industries_served: list[dict[str, Any]] = Field(default_factory=list)
    key_engagements: list[dict[str, Any]] = Field(default_factory=list)
    peer_review_status: str = ""
    quality_review_date: Optional[date] = None


class RfpBidUpdate(BaseModel):
    status: str


def _credential_health(row):
    if not row:
        return {"score": 0, "missing": ["firm_name", "partners", "fee_receipts", "peer_review_status"]}
    missing = []
    if not row.firm_name:
        missing.append("firm_name")
    if not row.partners:
        missing.append("partners")
    if not row.industries_served:
        missing.append("industries_served")
    if not row.key_engagements:
        missing.append("key_engagements")
    if not any(_num(value) > 0 for value in (row.gross_fee_receipts_fy1, row.gross_fee_receipts_fy2, row.gross_fee_receipts_fy3)):
        missing.append("fee_receipts")
    if str(row.peer_review_status or "").lower() not in ("valid", "active", "completed"):
        missing.append("peer_review_status")
    return {"score": round((6 - len(missing)) / 6 * 100, 1), "missing": missing}


def _credential_out(row):
    return {key: getattr(row, key) for key in CredentialRequest.model_fields} | {
        "id": str(row.id), "updated_at": _date(row.updated_at),
        "health": _credential_health(row),
    }


def _rfp_bid_out(row):
    eligibility = row.eligibility or {}
    criteria = eligibility.get("criteria") or []
    passed = sum(1 for item in criteria if item.get("eligible"))
    score = round(passed / max(len(criteria), 1) * 100, 1)
    return {
        "id": str(row.id), "title": row.title, "eligibility": eligibility,
        "proposal_text": row.proposal_text, "status": row.status, "created_at": _date(row.created_at),
        "criteria_count": len(criteria), "passed_count": passed,
        "gap_count": len(eligibility.get("disqualifying_gaps") or []),
        "eligibility_score": score, "proposal_ready": bool(row.proposal_text),
        "rfp_excerpt": (row.rfp_text or "")[:300],
    }


@router.get("/rfp/overview")
def rfp_overview(request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    bids = scoped(db, RfpBid, request.state.org_id).all()
    creds = scoped(db, FirmCredential, request.state.org_id).first()
    status_counts = {}
    for row in bids:
        status_counts[row.status] = status_counts.get(row.status, 0) + 1
    generated = status_counts.get("generated", 0) + status_counts.get("approved", 0)
    return {
        "total_bids": len(bids), "generated": generated,
        "ineligible": status_counts.get("ineligible", 0), "approved": status_counts.get("approved", 0),
        "rejected": status_counts.get("rejected", 0),
        "proposal_ready": sum(1 for row in bids if row.proposal_text),
        "average_score": round(sum(_rfp_bid_out(row)["eligibility_score"] for row in bids) / max(len(bids), 1), 1),
        "credential_health": _credential_health(creds),
        "status_counts": status_counts,
    }


@router.get("/rfp/credentials")
def get_credentials(request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    row = scoped(db, FirmCredential, request.state.org_id).first()
    return _credential_out(row) if row else None


@router.put("/rfp/credentials")
def put_credentials(payload: CredentialRequest, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    payload.firm_name = payload.firm_name.strip()
    if not payload.firm_name:
        raise HTTPException(400, "Firm name is required")
    if payload.founding_year < 1900 or payload.founding_year > date.today().year:
        raise HTTPException(422, "Founding year is invalid")
    if payload.total_staff < 0 or payload.article_clerks < 0:
        raise HTTPException(422, "Staff counts cannot be negative")
    row = scoped(db, FirmCredential, request.state.org_id).first()
    if not row:
        row = FirmCredential(org_id=request.state.org_id, firm_name=payload.firm_name)
        db.add(row)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return _credential_out(row)


class RfpRequest(BaseModel):
    title: str
    rfp_text: str


@router.get("/rfp/bids")
def rfp_bids(request: Request, skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    skip, limit = _page(skip, limit)
    return [_rfp_bid_out(row) for row in scoped(db, RfpBid, request.state.org_id).order_by(RfpBid.created_at.desc()).offset(skip).limit(limit).all()]


@router.post("/rfp/bids", status_code=201)
def analyze_rfp(payload: RfpRequest, request: Request, db: Session = Depends(get_db), user=Depends(require_role(["partner"]))):
    if not payload.title.strip() or len(payload.rfp_text.strip()) < 20:
        raise HTTPException(422, "RFP title and text are required")
    creds = scoped(db, FirmCredential, request.state.org_id).first()
    if not creds:
        raise HTTPException(400, "Save firm credentials before analyzing an RFP")
    eligibility = check_rfp_eligibility(payload.rfp_text, creds)
    proposal = generate_bid_proposal(payload.title, payload.rfp_text, eligibility, creds)
    row = RfpBid(org_id=request.state.org_id, title=payload.title, rfp_text=payload.rfp_text, eligibility=eligibility, proposal_text=proposal, status="generated" if proposal else "ineligible", created_by=user.id)
    db.add(row)
    _activity(db, request, user.id, "rfp_bid", None, 1800, {"title": payload.title})
    db.commit()
    db.refresh(row)
    return _rfp_bid_out(row)


@router.patch("/rfp/bids/{bid_id}")
def update_rfp_bid(bid_id: str, payload: RfpBidUpdate, request: Request, db: Session = Depends(get_db),
                   _=Depends(require_role(["partner"]))):
    row = scoped(db, RfpBid, request.state.org_id).filter(RfpBid.id == bid_id).first()
    if not row:
        raise HTTPException(404, "RFP bid not found")
    if payload.status not in ("generated", "approved", "rejected", "ineligible"):
        raise HTTPException(422, "Invalid bid status")
    if payload.status == "approved" and not row.proposal_text:
        raise HTTPException(422, "Only generated bids can be approved")
    row.status = payload.status
    db.commit()
    return _rfp_bid_out(row)


@router.get("/rfp/bids/{bid_id}/export")
def export_rfp(bid_id: str, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    row = scoped(db, RfpBid, request.state.org_id).filter(RfpBid.id == bid_id).first()
    if not row or not row.proposal_text:
        raise HTTPException(404, "Generated bid not found")
    data = build_text_docx(row.title, row.proposal_text)
    return StreamingResponse(io.BytesIO(data), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", headers={"Content-Disposition": f'attachment; filename="technical-bid-{bid_id}.docx"'})


class TimesheetRequest(BaseModel):
    client_id: str
    date: date
    hours_logged: float = Field(gt=0, le=24)
    task_description: str
    billable: bool = True
    billing_rate: float = 1500
    cost_rate: float = 800


class ActivityRequest(BaseModel):
    client_id: Optional[str] = None
    activity_type: str
    duration_seconds: int = Field(ge=0)
    details: dict[str, Any] = Field(default_factory=dict)


def _timesheet_entry_out(row, clients=None):
    client = (clients or {}).get(str(row.client_id))
    revenue = _num(row.hours_logged) * _num(row.billing_rate) if row.billable else 0
    cost = _num(row.hours_logged) * _num(row.cost_rate)
    return {
        "id": str(row.id), "user_id": str(row.user_id), "client_id": str(row.client_id),
        "client_name": client.name if client else "", "date": str(row.date),
        "hours_logged": _num(row.hours_logged), "task_description": row.task_description,
        "billable": row.billable, "billing_rate": _num(row.billing_rate), "cost_rate": _num(row.cost_rate),
        "revenue": round(revenue, 2), "cost": round(cost, 2), "margin": round(revenue - cost, 2),
    }


def _activity_out(row, clients=None):
    client = (clients or {}).get(str(row.client_id)) if row.client_id else None
    category = ACTIVITY_BILLING_MAP.get(row.activity_type, {"type": row.activity_type, "billable": False})
    return {
        "id": str(row.id), "user_id": str(row.user_id), "client_id": str(row.client_id) if row.client_id else None,
        "client_name": client.name if client else "", "activity_type": row.activity_type,
        "category": category.get("type"), "billable_activity": bool(category.get("billable")),
        "duration_seconds": row.duration_seconds, "hours": round((row.duration_seconds or 0) / 3600, 2),
        "details": row.details or {}, "created_at": _date(row.created_at),
    }


@router.post("/timesheets/entries", status_code=201)
def create_timesheet(payload: TimesheetRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _client(db, request.state.org_id, payload.client_id)
    if not payload.task_description.strip():
        raise HTTPException(400, "Task description is required")
    if payload.billing_rate < 0 or payload.cost_rate < 0:
        raise HTTPException(422, "Rates cannot be negative")
    row = TimesheetEntry(org_id=request.state.org_id, user_id=user.id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return _timesheet_entry_out(row)


@router.post("/timesheets/activities", status_code=201)
def create_activity(payload: ActivityRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    if payload.client_id:
        _client(db, request.state.org_id, payload.client_id)
    if payload.activity_type not in ACTIVITY_BILLING_MAP:
        raise HTTPException(422, "Unsupported activity type")
    _activity(db, request, user.id, payload.activity_type, payload.client_id, payload.duration_seconds, payload.details)
    db.commit()
    return {"created": True}


@router.get("/timesheets/entries")
def timesheet_entries(request: Request, month: str = "", client_id: str = "", skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, TimesheetEntry, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(TimesheetEntry.client_id == client_id)
    if month:
        start, end = _month_window(month)
        query = query.filter(TimesheetEntry.date >= start, TimesheetEntry.date < end)
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [_timesheet_entry_out(row, clients) for row in query.order_by(TimesheetEntry.date.desc()).offset(skip).limit(limit).all()]


@router.get("/timesheets/activities")
def timesheet_activities(request: Request, month: str = "", client_id: str = "", activity_type: str = "",
                         skip: int = 0, limit: int = 200, db: Session = Depends(get_db), _=Depends(get_current_user)):
    skip, limit = _page(skip, limit)
    query = scoped(db, UserActivityLog, request.state.org_id)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(UserActivityLog.client_id == client_id)
    if month:
        start, end = _month_window(month)
        query = query.filter(UserActivityLog.created_at >= start, UserActivityLog.created_at < end)
    if activity_type:
        query = query.filter(UserActivityLog.activity_type == activity_type)
    clients = {str(row.id): row for row in scoped(db, Client, request.state.org_id).all()}
    return [_activity_out(row, clients) for row in query.order_by(UserActivityLog.created_at.desc()).offset(skip).limit(limit).all()]


@router.delete("/timesheets/entries/{entry_id}", status_code=204)
def delete_timesheet(entry_id: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = scoped(db, TimesheetEntry, request.state.org_id).filter(TimesheetEntry.id == entry_id).first()
    if not row:
        raise HTTPException(404, "Timesheet entry not found")
    db.delete(row)
    db.commit()


@router.get("/timesheets/profitability")
def profitability(request: Request, month: str = "", db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    start, end = _month_window(month)
    clients = scoped(db, Client, request.state.org_id).all()
    client_names = {client.id: client.name for client in clients}

    billable_types = [key for key, value in ACTIVITY_BILLING_MAP.items() if value.get("billable")]
    activity_rows = (
        scoped(db, UserActivityLog, request.state.org_id)
        .with_entities(
            UserActivityLog.client_id,
            func.coalesce(func.sum(UserActivityLog.duration_seconds), 0).label("seconds"),
            func.coalesce(
                func.sum(
                    case(
                        (UserActivityLog.activity_type.in_(billable_types), UserActivityLog.duration_seconds),
                        else_=0,
                    )
                ),
                0,
            ).label("billable_seconds"),
        )
        .filter(
            UserActivityLog.client_id.isnot(None),
            UserActivityLog.created_at >= start,
            UserActivityLog.created_at < end,
        )
        .group_by(UserActivityLog.client_id)
        .all()
    )
    activities = {
        row.client_id: {
            "seconds": float(row.seconds or 0),
            "billable_seconds": float(row.billable_seconds or 0),
        }
        for row in activity_rows
    }

    breakdown_rows = (
        scoped(db, UserActivityLog, request.state.org_id)
        .with_entities(
            UserActivityLog.client_id,
            UserActivityLog.activity_type,
            func.coalesce(func.sum(UserActivityLog.duration_seconds), 0).label("seconds"),
        )
        .filter(
            UserActivityLog.client_id.isnot(None),
            UserActivityLog.created_at >= start,
            UserActivityLog.created_at < end,
        )
        .group_by(UserActivityLog.client_id, UserActivityLog.activity_type)
        .all()
    )
    breakdowns: dict[Any, dict[str, float]] = {}
    for row in breakdown_rows:
        category = ACTIVITY_BILLING_MAP.get(row.activity_type, {"type": row.activity_type})["type"]
        client_breakdown = breakdowns.setdefault(row.client_id, {})
        client_breakdown[category] = round(client_breakdown.get(category, 0) + float(row.seconds or 0) / 3600, 2)

    entry_rows = (
        scoped(db, TimesheetEntry, request.state.org_id)
        .with_entities(
            TimesheetEntry.client_id,
            func.coalesce(func.sum(TimesheetEntry.hours_logged), 0).label("logged_hours"),
            func.coalesce(
                func.sum(
                    case(
                        (TimesheetEntry.billable.is_(True), TimesheetEntry.hours_logged * TimesheetEntry.billing_rate),
                        else_=0,
                    )
                ),
                0,
            ).label("revenue"),
            func.coalesce(func.sum(TimesheetEntry.hours_logged * TimesheetEntry.cost_rate), 0).label("cost"),
        )
        .filter(TimesheetEntry.date >= start, TimesheetEntry.date < end)
        .group_by(TimesheetEntry.client_id)
        .all()
    )
    entries = {
        row.client_id: {
            "logged_hours": float(row.logged_hours or 0),
            "revenue": float(row.revenue or 0),
            "cost": float(row.cost or 0),
        }
        for row in entry_rows
    }

    result = []
    for client in clients:
        activity = activities.get(client.id, {})
        entry = entries.get(client.id, {})
        seconds = activity.get("seconds", 0)
        billable_seconds = activity.get("billable_seconds", 0)
        actual_hours = round(seconds / 3600, 2)
        logged_hours = round(entry.get("logged_hours", 0), 2)
        revenue = round(entry.get("revenue", 0), 2)
        cost = round(entry.get("cost", 0), 2)
        result.append({
            "client_id": str(client.id),
            "client_name": client_names[client.id],
            "actual_hours": actual_hours,
            "logged_hours": logged_hours,
            "billable_hours": round(billable_seconds / 3600, 2),
            "variance_hours": round(actual_hours - logged_hours, 2),
            "utilization_pct": round(billable_seconds / max(seconds, 1) * 100, 1),
            "revenue": revenue,
            "cost": cost,
            "margin": round(revenue - cost, 2),
            "task_breakdown": breakdowns.get(client.id, {}),
        })
    return sorted(result, key=lambda row: row["margin"])


@router.get("/timesheets/overview")
def timesheet_overview(request: Request, month: str = "", db: Session = Depends(get_db), _=Depends(require_role(["partner"]))):
    rows = profitability(request, month, db, _)
    return {
        "client_count": len(rows),
        "actual_hours": round(sum(row["actual_hours"] for row in rows), 2),
        "logged_hours": round(sum(row["logged_hours"] for row in rows), 2),
        "billable_hours": round(sum(row["billable_hours"] for row in rows), 2),
        "variance_hours": round(sum(row["variance_hours"] for row in rows), 2),
        "revenue": round(sum(row["revenue"] for row in rows), 2),
        "cost": round(sum(row["cost"] for row in rows), 2),
        "margin": round(sum(row["margin"] for row in rows), 2),
        "utilization_pct": round(sum(row["billable_hours"] for row in rows) / max(sum(row["actual_hours"] for row in rows), 0.01) * 100, 1),
        "negative_margin_clients": sum(1 for row in rows if row["margin"] < 0),
        "unlogged_actual_hours": round(sum(max(row["variance_hours"], 0) for row in rows), 2),
        "top_loss_clients": [row for row in rows if row["margin"] < 0][:5],
    }
