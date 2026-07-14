"""APIs for the CA Exception Autopilot."""
from datetime import datetime, timezone
import time
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.engines.autopilot_engine import (
    ACTIVE_STATUSES,
    MANAGED_SOURCE_TYPES,
    TALLY_FIELD_MAP,
    build_exception_candidates,
    import_tally_records,
    refresh_autopilot_exceptions,
    summarize_autopilot,
)
from app.models.anomaly_flag import AnomalyFlag
from app.models.autopilot import (
    AutopilotException, AutopilotFollowup, AutopilotReviewAction, AutopilotSyncRun,
)
from app.models.client import Client
from app.models.extensions import CertificateRecord, LeaseRecord, RfpBid, SecretarialDocument
from app.models.user import User
from app.utils.activity import log_activity
from app.utils.events import publish_event
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped

router = APIRouter()
EXCEPTION_STATUSES = {"open", "in_review", "approved", "resolved", "dismissed"}
SEVERITIES = {"critical", "high", "medium", "low"}
FOLLOWUP_CHANNELS = {"whatsapp", "email", "phone"}


class TallySyncRequest(BaseModel):
    client_id: str
    source_name: str = Field(default="TallyPrime", min_length=1, max_length=80)
    period: Optional[str] = None
    records: list[dict[str, Any]] = Field(default_factory=list, max_length=5000)


class RefreshRequest(BaseModel):
    client_id: Optional[str] = None
    dry_run: bool = False


class ExceptionUpdate(BaseModel):
    status: Optional[str] = None
    owner_id: Optional[str] = None
    clear_owner: bool = False
    action_type: str = Field(default="review_note", min_length=1, max_length=30)
    notes: str = Field(default="", max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)


class FollowupRequest(BaseModel):
    client_id: Optional[str] = None
    exception_id: Optional[str] = None
    channel: str = Field(default="whatsapp", min_length=1, max_length=20)
    template: str = Field(default="autopilot_document_request", min_length=1, max_length=60)
    message: str = Field(default="", max_length=2000)
    send_now: bool = False


def _num(value):
    return float(value or 0)


def _date(value):
    return value.isoformat() if value else None


def _client(db: Session, org_id: str, client_id: str) -> Client:
    row = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not row:
        raise HTTPException(404, "Client not found")
    return row


def _exception(db: Session, org_id: str, exception_id: str) -> AutopilotException:
    row = scoped(db, AutopilotException, org_id).filter(AutopilotException.id == exception_id).first()
    if not row:
        raise HTTPException(404, "Autopilot exception not found")
    return row


def _active_exception_query(db: Session, org_id: str, client_id: str | None = None):
    query = scoped(db, AutopilotException, org_id).filter(AutopilotException.status.in_(ACTIVE_STATUSES))
    if client_id:
        query = query.filter(AutopilotException.client_id == client_id)
    return query


def _refresh_snapshot(db: Session, org_id: str, client_id: str | None = None) -> dict[str, Any]:
    rows = _active_exception_query(db, org_id, client_id).all()
    return {
        "open_count": len(rows),
        "critical_count": sum(1 for row in rows if row.severity == "critical"),
        "high_count": sum(1 for row in rows if row.severity == "high"),
        "total_impact": sum(_num(row.impact_amount) for row in rows),
    }


def _preview_refresh(db: Session, org_id: str, client_id: str | None = None) -> dict[str, Any]:
    candidates = build_exception_candidates(db, org_id, client_id)
    candidate_fingerprints = {candidate["fingerprint"] for candidate in candidates}
    active_managed = _active_exception_query(db, org_id, client_id).filter(
        AutopilotException.source_type.in_(MANAGED_SOURCE_TYPES),
    ).all()
    active_by_fingerprint = {row.fingerprint: row for row in active_managed}
    created = sum(1 for fingerprint in candidate_fingerprints if fingerprint not in active_by_fingerprint)
    updated = sum(1 for fingerprint in candidate_fingerprints if fingerprint in active_by_fingerprint)
    auto_resolved = sum(1 for row in active_managed if row.fingerprint not in candidate_fingerprints)
    before = _refresh_snapshot(db, org_id, client_id)
    return {
        "created": created,
        "updated": updated,
        "skipped_closed": 0,
        "auto_resolved": auto_resolved,
        "candidate_count": len(candidates),
        "before": before,
        "after": {
            **before,
            "open_count": max(0, before["open_count"] + created - auto_resolved),
        },
    }


def _exception_out(
    row: AutopilotException,
    client_name: str = "",
    owner_email: str = "",
    reviewed_by_email: str = "",
) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "client_id": str(row.client_id) if row.client_id else None,
        "client_name": client_name,
        "source_type": row.source_type,
        "source_id": str(row.source_id) if row.source_id else None,
        "title": row.title,
        "description": row.description,
        "severity": row.severity,
        "impact_amount": _num(row.impact_amount),
        "due_date": str(row.due_date) if row.due_date else None,
        "status": row.status,
        "owner_id": str(row.owner_id) if row.owner_id else None,
        "owner_email": owner_email,
        "evidence": row.evidence or {},
        "recommended_actions": row.recommended_actions or [],
        "generated_at": _date(row.generated_at),
        "updated_at": _date(row.updated_at),
        "reviewed_by": str(row.reviewed_by) if row.reviewed_by else None,
        "reviewed_by_email": reviewed_by_email,
        "reviewed_at": _date(row.reviewed_at),
    }


def _sync_run_out(row: AutopilotSyncRun, client_name: str = "") -> dict[str, Any]:
    return {
        "id": str(row.id),
        "client_id": str(row.client_id) if row.client_id else None,
        "client_name": client_name,
        "source": row.source,
        "source_name": row.source_name,
        "period": row.period,
        "status": row.status,
        "records_received": row.records_received,
        "records_imported": row.records_imported,
        "records_failed": row.records_failed,
        "summary": row.summary or {},
        "started_at": _date(row.started_at),
        "completed_at": _date(row.completed_at),
    }


@router.get("/overview")
def overview(
    request: Request,
    auto_refresh: bool = True,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if auto_refresh:
        refresh_autopilot_exceptions(db, request.state.org_id)
        db.commit()
    clients = {str(row.id): row.name for row in scoped(db, Client, request.state.org_id).all()}
    users = {str(row.id): row.email for row in scoped(db, User, request.state.org_id).all()}
    exceptions = scoped(db, AutopilotException, request.state.org_id).filter(
        AutopilotException.status.in_(["open", "in_review"]),
    ).order_by(AutopilotException.updated_at.desc()).all()
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    exceptions = sorted(exceptions, key=lambda row: (
        severity_rank.get(row.severity, 9),
        row.due_date.isoformat() if row.due_date else "9999-12-31",
        -_num(row.impact_amount),
    ))
    last_sync = scoped(db, AutopilotSyncRun, request.state.org_id).order_by(
        AutopilotSyncRun.started_at.desc(),
    ).limit(5).all()
    return {
        "summary": summarize_autopilot(db, request.state.org_id),
        "exceptions": [
            _exception_out(
                row,
                clients.get(str(row.client_id), ""),
                users.get(str(row.owner_id), "") if row.owner_id else "",
                users.get(str(row.reviewed_by), "") if row.reviewed_by else "",
            )
            for row in exceptions[:50]
        ],
        "last_sync_runs": [_sync_run_out(row) for row in last_sync],
    }


@router.post("/refresh")
def refresh_inbox(
    request: Request,
    payload: RefreshRequest | None = Body(default=None),
    client_id: str = "",
    db: Session = Depends(get_db),
    user=Depends(require_role(["partner", "manager"])),
):
    scope_client_id = client_id or (payload.client_id if payload else "") or ""
    scope_client = _client(db, request.state.org_id, scope_client_id) if scope_client_id else None
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    before = _refresh_snapshot(db, request.state.org_id, scope_client_id or None)
    if payload and payload.dry_run:
        result = _preview_refresh(db, request.state.org_id, scope_client_id or None)
    else:
        result = refresh_autopilot_exceptions(db, request.state.org_id, scope_client_id or None)
        db.flush()
        result["before"] = before
        result["after"] = _refresh_snapshot(db, request.state.org_id, scope_client_id or None)
    result.update({
        "dry_run": bool(payload and payload.dry_run),
        "scope": {
            "client_id": scope_client_id or None,
            "client_name": scope_client.name if scope_client else "All clients",
        },
        "started_at": started_at.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "duration_ms": round((time.perf_counter() - started) * 1000),
    })
    log_activity(db, request.state.org_id, user.id, "autopilot_refresh", scope_client_id or None, 120, result)
    if not result["dry_run"]:
        db.commit()
    return result


@router.get("/exceptions")
def list_exceptions(
    request: Request,
    status: str = "open,in_review",
    severity: str = "",
    source_type: str = "",
    client_id: str = "",
    skip: int = 0,
    limit: int = 250,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 1000:
        raise HTTPException(422, "limit must be between 1 and 1000")
    clients = {str(row.id): row.name for row in scoped(db, Client, request.state.org_id).all()}
    users = {str(row.id): row.email for row in scoped(db, User, request.state.org_id).all()}
    query = scoped(db, AutopilotException, request.state.org_id)
    if status:
        statuses = [item.strip() for item in status.split(",") if item.strip()]
        if any(item not in EXCEPTION_STATUSES for item in statuses):
            raise HTTPException(422, "Invalid exception status")
        query = query.filter(AutopilotException.status.in_(statuses))
    if severity:
        if severity not in SEVERITIES:
            raise HTTPException(422, "Invalid severity")
        query = query.filter(AutopilotException.severity == severity)
    if source_type:
        query = query.filter(AutopilotException.source_type == source_type)
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(AutopilotException.client_id == client_id)
    rows = query.order_by(AutopilotException.updated_at.desc()).offset(skip).limit(limit).all()
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows = sorted(rows, key=lambda row: (
        severity_rank.get(row.severity, 9),
        row.due_date.isoformat() if row.due_date else "9999-12-31",
        -_num(row.impact_amount),
    ))
    return [
        _exception_out(
            row,
            clients.get(str(row.client_id), ""),
            users.get(str(row.owner_id), "") if row.owner_id else "",
            users.get(str(row.reviewed_by), "") if row.reviewed_by else "",
        )
        for row in rows
    ]


@router.get("/exceptions/{exception_id}")
def get_exception(exception_id: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    row = _exception(db, request.state.org_id, exception_id)
    client_name = ""
    if row.client_id:
        client = scoped(db, Client, request.state.org_id).filter(Client.id == row.client_id).first()
        client_name = client.name if client else ""
    users = {str(user.id): user.email for user in scoped(db, User, request.state.org_id).all()}
    actions = scoped(db, AutopilotReviewAction, request.state.org_id).filter(
        AutopilotReviewAction.exception_id == row.id,
    ).order_by(AutopilotReviewAction.created_at.desc()).all()
    followups = scoped(db, AutopilotFollowup, request.state.org_id).filter(
        AutopilotFollowup.exception_id == row.id,
    ).order_by(AutopilotFollowup.created_at.desc()).all()
    return {
        **_exception_out(
            row,
            client_name,
            users.get(str(row.owner_id), "") if row.owner_id else "",
            users.get(str(row.reviewed_by), "") if row.reviewed_by else "",
        ),
        "actions": [{
            "id": str(action.id),
            "action_type": action.action_type,
            "notes": action.notes,
            "payload": action.payload or {},
            "created_by": str(action.created_by) if action.created_by else None,
            "created_by_email": users.get(str(action.created_by), "") if action.created_by else "",
            "created_at": _date(action.created_at),
        } for action in actions],
        "followups": [_followup_out(item) for item in followups],
    }


@router.patch("/exceptions/{exception_id}")
def update_exception(
    exception_id: str,
    payload: ExceptionUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_role(["partner", "manager"])),
):
    row = _exception(db, request.state.org_id, exception_id)
    if payload.status:
        if payload.status not in EXCEPTION_STATUSES:
            raise HTTPException(422, "Invalid exception status")
        row.status = payload.status
        if payload.status in ("approved", "resolved", "dismissed"):
            row.reviewed_by = user.id
            row.reviewed_at = datetime.now(timezone.utc)
        elif payload.status in ACTIVE_STATUSES:
            row.reviewed_by = None
            row.reviewed_at = None
    if payload.clear_owner:
        row.owner_id = None
    elif payload.owner_id:
        owner = scoped(db, User, request.state.org_id).filter(User.id == payload.owner_id).first()
        if not owner:
            raise HTTPException(404, "Owner not found")
        row.owner_id = payload.owner_id
    action = AutopilotReviewAction(
        org_id=request.state.org_id,
        exception_id=row.id,
        action_type=payload.action_type,
        notes=payload.notes,
        payload=payload.payload,
        created_by=user.id,
    )
    db.add(action)
    _apply_cross_module_review(db, request.state.org_id, row, payload.status)
    log_activity(db, request.state.org_id, user.id, "autopilot_review", str(row.client_id) if row.client_id else None, 300, {
        "exception_id": str(row.id),
        "status": payload.status,
        "action_type": payload.action_type,
    })
    db.commit()
    owner_email = ""
    reviewed_by_email = ""
    if row.owner_id:
        owner = scoped(db, User, request.state.org_id).filter(User.id == row.owner_id).first()
        owner_email = owner.email if owner else ""
    if row.reviewed_by:
        reviewer = scoped(db, User, request.state.org_id).filter(User.id == row.reviewed_by).first()
        reviewed_by_email = reviewer.email if reviewer else ""
    return _exception_out(row, owner_email=owner_email, reviewed_by_email=reviewed_by_email)


def _apply_cross_module_review(db: Session, org_id: str, row: AutopilotException, status: str | None):
    if status not in ("approved", "resolved", "dismissed"):
        return
    if row.source_type == "anomaly" and row.source_id:
        flag = scoped(db, AnomalyFlag, org_id).filter(AnomalyFlag.id == row.source_id).first()
        if flag:
            flag.reviewed = True
    elif row.source_type == "certificate_review" and row.source_id and status == "approved":
        cert = scoped(db, CertificateRecord, org_id).filter(CertificateRecord.id == row.source_id).first()
        if cert:
            cert.status = "approved"
    elif row.source_type == "secretarial_review" and row.source_id and status == "approved":
        doc = scoped(db, SecretarialDocument, org_id).filter(SecretarialDocument.id == row.source_id).first()
        if doc:
            doc.status = "approved"
    elif row.source_type == "lease_review" and row.source_id and status == "approved":
        lease = scoped(db, LeaseRecord, org_id).filter(LeaseRecord.id == row.source_id).first()
        if lease:
            lease.verified = True
    elif row.source_type == "rfp_review" and row.source_id and status == "approved":
        bid = scoped(db, RfpBid, org_id).filter(RfpBid.id == row.source_id).first()
        if bid:
            bid.status = "approved"


@router.get("/tally/connector-config")
def tally_connector_config(request: Request, _=Depends(get_current_user)):
    base_url = str(request.base_url).rstrip("/")
    canonical_fields: dict[str, dict[str, Any]] = {
        "invoice_no": {"required": True, "type": "string", "description": "Voucher, invoice, or bill number."},
        "date": {"required": True, "type": "date", "formats": ["YYYY-MM-DD", "DD/MM/YYYY", "DD-MM-YYYY", "DD MMM YYYY"]},
        "amount": {"required": True, "type": "number", "description": "Gross or taxable voucher amount in INR."},
        "vendor_name": {"required": False, "type": "string", "description": "Ledger, party, supplier, or vendor name."},
        "vendor_gstin": {"required": False, "type": "string", "description": "Party GSTIN/UIN where available."},
        "tax_amount": {"required": False, "type": "number", "description": "GST amount where exported separately."},
    }
    aliases: dict[str, list[str]] = {}
    for source_field, canonical in sorted(TALLY_FIELD_MAP.items()):
        aliases.setdefault(canonical, []).append(source_field)
    return {
        "connector_name": "CA Copilot Tally Connector",
        "version": "2026.06",
        "environment": settings.ENV,
        "sync_url": f"{base_url}/autopilot/tally/sync",
        "method": "POST",
        "content_type": "application/json",
        "headers": {
            "Authorization": "Bearer <access_token>",
            "Content-Type": "application/json",
        },
        "auth": {
            "type": "bearer_token",
            "token_source": "Login response access_token",
            "refresh_required": True,
        },
        "limits": {
            "max_records_per_request": 5000,
            "recommended_batch_size": 1000,
            "idempotency": "Duplicate vouchers are de-duplicated by org, client, source, invoice number, GSTIN, amount and date.",
        },
        "supported_sources": [
            {"key": "tally_prime", "label": "TallyPrime JSON/CSV export"},
            {"key": "tally_erp9", "label": "Tally ERP 9 CSV export"},
            {"key": "manual_json", "label": "Manual JSON paste or connector bridge"},
        ],
        "required_fields": ["client_id", "records[].invoice_no", "records[].amount", "records[].date"],
        "canonical_fields": canonical_fields,
        "field_aliases": aliases,
        "validation_rules": [
            "records must be a non-empty JSON array",
            "invoice_no, amount and date are mandatory for each accepted row",
            "amount may include commas, INR, Rs, or decimal notation",
            "unsupported columns are preserved only when mapped to canonical fields",
            "amounts between INR 45,000 and 49,999 are flagged for threshold-gaming review",
        ],
        "sample_request": {
            "client_id": "<client_id>",
            "source_name": "Apex TallyPrime desktop",
            "period": "2026-06",
            "records": [{
                "Voucher No": "PUR-1042",
                "Date": "05/06/2026",
                "Party Name": "Demo Supplier Pvt Ltd",
                "GSTIN/UIN of Party": "27ABCDE1234F1Z5",
                "Amount": "49,500",
                "Tax Amount": "8,910",
            }],
        },
        "sample_record": {
            "Voucher No": "PUR-1042",
            "Date": "05/06/2026",
            "Party Name": "Demo Supplier Pvt Ltd",
            "GSTIN/UIN of Party": "27ABCDE1234F1Z5",
            "Amount": "49,500",
            "Tax Amount": "8,910",
        },
        "sample_success_shape": {
            "sync_run": {"status": "completed", "records_imported": 1, "records_failed": 0},
            "failed": [],
            "autopilot_refresh": {"candidate_count": 1, "created": 1, "updated": 0},
        },
    }


@router.post("/tally/sync", status_code=201)
def tally_sync(
    payload: TallySyncRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_role(["partner", "manager"])),
):
    if not payload.records:
        raise HTTPException(400, "At least one Tally record is required")
    _client(db, request.state.org_id, payload.client_id)
    run, failed = import_tally_records(
        db, request.state.org_id, payload.client_id, payload.records,
        source_name=payload.source_name, period=payload.period, user_id=str(user.id),
    )
    db.flush()
    refresh_result = refresh_autopilot_exceptions(db, request.state.org_id, payload.client_id)
    log_activity(db, request.state.org_id, user.id, "tally_sync", payload.client_id, 900, {
        "run_id": str(run.id),
        "records": len(payload.records),
        "failed": len(failed),
    })
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="integration.tally.sync_completed" if run.status == "completed" else "integration.tally.sync_degraded",
        aggregate_type="autopilot_sync_run",
        aggregate_id=str(run.id),
        source_module="autopilot",
        payload={
            "client_id": payload.client_id,
            "source_name": payload.source_name,
            "period": payload.period,
            "records_received": run.records_received,
            "records_imported": run.records_imported,
            "records_failed": run.records_failed,
            "failed_samples": failed[:5],
        },
        status="recorded" if run.status == "completed" else "failed",
    )
    db.commit()
    db.refresh(run)
    return {"sync_run": _sync_run_out(run), "failed": failed, "autopilot_refresh": refresh_result}


@router.get("/sync-runs")
def sync_runs(
    request: Request,
    client_id: str = "",
    status: str = "",
    source: str = "",
    period: str = "",
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    query = scoped(db, AutopilotSyncRun, request.state.org_id)
    clients = {str(row.id): row.name for row in scoped(db, Client, request.state.org_id).all()}
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(AutopilotSyncRun.client_id == client_id)
    if status:
        query = query.filter(AutopilotSyncRun.status == status)
    if source:
        query = query.filter(AutopilotSyncRun.source == source)
    if period:
        query = query.filter(AutopilotSyncRun.period == period)
    rows = query.order_by(AutopilotSyncRun.started_at.desc()).offset(skip).limit(limit).all()
    totals = {
        "runs": len(rows),
        "records_received": sum(row.records_received or 0 for row in rows),
        "records_imported": sum(row.records_imported or 0 for row in rows),
        "records_failed": sum(row.records_failed or 0 for row in rows),
        "failed_runs": sum(1 for row in rows if row.status in {"failed", "completed_with_errors"}),
    }
    return {
        "items": [_sync_run_out(row, clients.get(str(row.client_id), "")) for row in rows],
        "totals": totals,
        "skip": skip,
        "limit": limit,
    }


@router.post("/followups", status_code=201)
def create_followup(
    payload: FollowupRequest,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_role(["partner", "manager"])),
):
    exception = None
    client_id = payload.client_id
    if payload.exception_id:
        exception = _exception(db, request.state.org_id, payload.exception_id)
        client_id = client_id or (str(exception.client_id) if exception.client_id else None)
    if not client_id:
        raise HTTPException(400, "client_id is required when no client-linked exception is provided")
    client = _client(db, request.state.org_id, client_id)
    if payload.channel not in FOLLOWUP_CHANNELS:
        raise HTTPException(422, "Invalid follow-up channel")
    message = payload.message or _default_followup_message(client, exception)
    status = "draft"
    sent_at = None
    if payload.send_now:
        status, sent_at = _try_send_followup(client, payload.channel, message)
    row = AutopilotFollowup(
        org_id=request.state.org_id, client_id=client.id,
        exception_id=exception.id if exception else None,
        channel=payload.channel, template=payload.template,
        message=message, status=status, sent_at=sent_at, created_by=user.id,
    )
    db.add(row)
    if exception and exception.status == "open":
        exception.status = "in_review"
    log_activity(db, request.state.org_id, user.id, "autopilot_followup", str(client.id), 300, {
        "exception_id": str(exception.id) if exception else None,
        "channel": payload.channel,
        "status": status,
    })
    db.commit()
    db.refresh(row)
    return _followup_out(row)


def _default_followup_message(client: Client, exception: AutopilotException | None) -> str:
    if not exception:
        return f"Dear {client.name}, please share the pending accounting and compliance documents requested by our office."
    return (
        f"Dear {client.name}, our review has identified this pending item: {exception.title}. "
        "Please share the required supporting documents or confirmation so we can close the matter."
    )


def _try_send_followup(client: Client, channel: str, message: str):
    if channel != "whatsapp":
        return "ready", None
    if not client.whatsapp_consent_at or not client.whatsapp_number:
        return "blocked_no_consent", None
    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_ID:
        return "ready_provider_missing", None
    try:
        from app.services.whatsapp_service import send_text
        send_text(client.whatsapp_number, message)
        return "sent", datetime.now(timezone.utc)
    except Exception:
        return "failed", None


@router.get("/followups")
def list_followups(
    request: Request,
    client_id: str = "",
    status: str = "",
    channel: str = "",
    exception_id: str = "",
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    query = scoped(db, AutopilotFollowup, request.state.org_id)
    clients = {str(row.id): row.name for row in scoped(db, Client, request.state.org_id).all()}
    exceptions = {
        str(row.id): row.title
        for row in scoped(db, AutopilotException, request.state.org_id).all()
    }
    if client_id:
        _client(db, request.state.org_id, client_id)
        query = query.filter(AutopilotFollowup.client_id == client_id)
    if status:
        query = query.filter(AutopilotFollowup.status == status)
    if channel:
        if channel not in FOLLOWUP_CHANNELS:
            raise HTTPException(422, "Invalid follow-up channel")
        query = query.filter(AutopilotFollowup.channel == channel)
    if exception_id:
        _exception(db, request.state.org_id, exception_id)
        query = query.filter(AutopilotFollowup.exception_id == exception_id)
    rows = query.order_by(AutopilotFollowup.created_at.desc()).offset(skip).limit(limit).all()
    by_status: dict[str, int] = {}
    by_channel: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_channel[row.channel] = by_channel.get(row.channel, 0) + 1
    return {
        "items": [
            _followup_out(
                row,
                clients.get(str(row.client_id), ""),
                exceptions.get(str(row.exception_id), "") if row.exception_id else "",
            )
            for row in rows
        ],
        "totals": {
            "followups": len(rows),
            "by_status": by_status,
            "by_channel": by_channel,
            "blocked": sum(count for value, count in by_status.items() if value in {"blocked_no_consent", "ready_provider_missing", "failed"}),
        },
        "skip": skip,
        "limit": limit,
    }


def _followup_out(row: AutopilotFollowup, client_name: str = "", exception_title: str = "") -> dict[str, Any]:
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": client_name,
        "exception_id": str(row.exception_id) if row.exception_id else None,
        "exception_title": exception_title,
        "channel": row.channel,
        "template": row.template,
        "message": row.message,
        "status": row.status,
        "scheduled_at": _date(row.scheduled_at),
        "sent_at": _date(row.sent_at),
        "response_summary": row.response_summary,
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": _date(row.created_at),
    }
