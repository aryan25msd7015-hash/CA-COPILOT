from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import io
from typing import List, Optional

from app.database import get_db
from app.models.transaction import Transaction
from app.models.client import Client
from app.models.reconciliation import ReconciliationConfig, ReconciliationMatchAction, ReconciliationResult
from app.schemas.reconciliation import (
    ManualMatchRequest,
    ReconciliationRunRequest, ReconciliationConfigOut,
    ReconciliationConfigUpdate, ReconciliationResultOut, UnmatchRequest,
)
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped
from app.utils.activity import log_activity
from app.utils.events import publish_event

router = APIRouter()
MATCH_STATUSES = {"unmatched", "exact", "tolerance", "fuzzy"}
TRANSACTION_SOURCES = {"upload", "gstr2b"}


def _client_or_404(db: Session, org_id, client_id: str) -> Client:
    client = scoped(db, Client, org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    return client


def _transaction_or_404(db: Session, org_id, transaction_id: str) -> Transaction:
    txn = scoped(db, Transaction, org_id).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return txn


def _action_out(row: ReconciliationMatchAction) -> dict:
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "result_id": str(row.result_id) if row.result_id else None,
        "purchase_transaction_id": str(row.purchase_transaction_id),
        "gstr2b_transaction_id": str(row.gstr2b_transaction_id) if row.gstr2b_transaction_id else None,
        "action_type": row.action_type,
        "previous_status": row.previous_status,
        "previous_confidence": float(row.previous_confidence) if row.previous_confidence is not None else None,
        "new_status": row.new_status,
        "new_confidence": float(row.new_confidence) if row.new_confidence is not None else None,
        "reason": row.reason,
        "evidence": row.evidence,
        "created_by_user_id": str(row.created_by_user_id) if row.created_by_user_id else None,
        "created_at": row.created_at,
    }


def _refresh_result_counts(db: Session, result: ReconciliationResult | None) -> None:
    if not result:
        return
    from app.tasks.reconciliation_tasks import _period_bounds

    query = scoped(db, Transaction, result.org_id).filter(
        Transaction.client_id == result.client_id,
        Transaction.source == "upload",
    )
    bounds = _period_bounds(result.period)
    if bounds:
        query = query.filter(Transaction.date.between(*bounds))
    rows = query.all()
    matched = [row for row in rows if row.match_status in {"exact", "tolerance", "fuzzy"}]
    result.matched_count = len(matched)
    result.unmatched_count = len([row for row in rows if row.match_status == "unmatched"])
    total_purchase = sum(float(row.amount or 0) for row in rows)
    matched_value = sum(float(row.amount or 0) for row in matched)
    result.total_purchase = total_purchase
    result.mismatch_value = total_purchase - matched_value
    result.input_summary = {**(result.input_summary or {}), "manual_adjusted": True, "matched_value": matched_value}


@router.post("/run")
def run_reconciliation(req: ReconciliationRunRequest, request: Request,
                       db: Session = Depends(get_db), user=Depends(get_current_user)):
    client = _client_or_404(db, request.state.org_id, req.client_id)
    from app.tasks.reconciliation_tasks import _period_bounds

    bounds = _period_bounds(req.period)
    if not bounds:
        raise HTTPException(422, "Invalid period")

    running = (
        scoped(db, ReconciliationResult, request.state.org_id)
        .filter(
            ReconciliationResult.client_id == req.client_id,
            ReconciliationResult.period == req.period,
            ReconciliationResult.status.in_(["queued", "running"]),
        )
        .order_by(ReconciliationResult.run_at.desc())
        .first()
    )
    if running:
        return {
            "task_id": running.task_id,
            "result_id": str(running.id),
            "status": running.status,
            "message": "Reconciliation already queued",
            "input_summary": running.input_summary or {},
        }

    purchase_query = scoped(db, Transaction, request.state.org_id).filter(
        Transaction.client_id == req.client_id,
        Transaction.source == "upload",
        Transaction.date.between(*bounds),
    )
    gstr2b_query = scoped(db, Transaction, request.state.org_id).filter(
        Transaction.client_id == req.client_id,
        Transaction.source == "gstr2b",
        Transaction.date.between(*bounds),
    )
    purchase_count = purchase_query.count()
    gstr2b_count = gstr2b_query.count()
    if purchase_count == 0 and gstr2b_count == 0:
        raise HTTPException(409, "No purchase or GSTR-2B transactions found for this period")

    purchase_total = float(purchase_query.with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar() or 0)
    gstr2b_total = float(gstr2b_query.with_entities(func.coalesce(func.sum(Transaction.amount), 0)).scalar() or 0)
    result = ReconciliationResult(
        org_id=client.org_id,
        client_id=req.client_id,
        period=req.period,
        status="queued",
        total_purchase=purchase_total,
        total_gstr2b=gstr2b_total,
        matched_count=0,
        unmatched_count=0,
        mismatch_value=purchase_total,
        input_summary={
            "purchase_count": purchase_count,
            "gstr2b_count": gstr2b_count,
            "purchase_total": purchase_total,
            "gstr2b_total": gstr2b_total,
        },
    )
    db.add(result)
    db.flush()
    from app.tasks.reconciliation_tasks import run_reconciliation as _task
    task = _task.delay(req.client_id, req.period, str(result.id))
    result.task_id = task.id
    log_activity(db, request.state.org_id, user.id, "reconciliation_run", req.client_id, 1800, {"period": req.period})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="reconciliation.queued",
        aggregate_type="reconciliation_result",
        aggregate_id=str(result.id),
        source_module="reconciliation",
        payload={"client_id": req.client_id, "period": req.period, "task_id": task.id, "input_summary": result.input_summary},
    )
    db.commit()
    return {
        "task_id": task.id,
        "result_id": str(result.id),
        "status": result.status,
        "message": "Reconciliation queued",
        "input_summary": result.input_summary,
    }


@router.get("/results/{client_id}", response_model=List[ReconciliationResultOut])
def get_results(client_id: str, request: Request, db: Session = Depends(get_db),
                skip: int = 0, limit: int = 10, _=Depends(get_current_user)):
    _client_or_404(db, request.state.org_id, client_id)
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 100:
        raise HTTPException(422, "limit must be between 1 and 100")
    return (scoped(db, ReconciliationResult, request.state.org_id)
            .filter(ReconciliationResult.client_id == client_id)
            .order_by(ReconciliationResult.run_at.desc())
            .offset(skip).limit(limit).all())


@router.get("/transactions")
def list_transactions(request: Request, db: Session = Depends(get_db),
                      client_id: Optional[str] = None,
                      match_status: Optional[str] = None,
                      source: Optional[str] = None,
                      period: Optional[str] = None,
                      skip: int = 0, limit: int = 100,
                      _=Depends(get_current_user)):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    q = scoped(db, Transaction, request.state.org_id)
    if client_id:
        _client_or_404(db, request.state.org_id, client_id)
        q = q.filter(Transaction.client_id == client_id)
    if match_status:
        if match_status not in MATCH_STATUSES:
            raise HTTPException(422, "Invalid match_status")
        q = q.filter(Transaction.match_status == match_status)
    if source:
        if source not in TRANSACTION_SOURCES:
            raise HTTPException(422, "Invalid transaction source")
        q = q.filter(Transaction.source == source)
    if period:
        from app.tasks.reconciliation_tasks import _period_bounds
        bounds = _period_bounds(period)
        if not bounds:
            raise HTTPException(422, "Invalid period")
        q = q.filter(Transaction.date.between(*bounds))
    rows = q.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": str(r.id), "document_id": str(r.document_id) if r.document_id else None,
            "invoice_no": r.invoice_no,
            "vendor_name": r.vendor_name, "vendor_gstin": r.vendor_gstin,
            "amount": float(r.amount or 0), "date": str(r.date),
            "source": r.source,
            "match_status": r.match_status, "match_confidence": r.match_confidence,
            "anomaly_score": float(r.anomaly_score) if r.anomaly_score else None,
            "fraud_flag": r.fraud_flag,
        }
        for r in rows
    ]


@router.post("/manual-match")
def manual_match(payload: ManualMatchRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    purchase = _transaction_or_404(db, request.state.org_id, payload.purchase_transaction_id)
    if purchase.source != "upload":
        raise HTTPException(422, "purchase_transaction_id must refer to a purchase register transaction")
    gstr2b = None
    if payload.gstr2b_transaction_id:
        gstr2b = _transaction_or_404(db, request.state.org_id, payload.gstr2b_transaction_id)
        if gstr2b.client_id != purchase.client_id or gstr2b.source != "gstr2b":
            raise HTTPException(422, "gstr2b_transaction_id must refer to the same client's GSTR-2B transaction")
    result = None
    if payload.result_id:
        result = scoped(db, ReconciliationResult, request.state.org_id).filter(ReconciliationResult.id == payload.result_id).first()
        if not result:
            raise HTTPException(404, "Reconciliation result not found")

    action = ReconciliationMatchAction(
        org_id=request.state.org_id,
        client_id=purchase.client_id,
        result_id=result.id if result else None,
        purchase_transaction_id=purchase.id,
        gstr2b_transaction_id=gstr2b.id if gstr2b else None,
        action_type="manual_match",
        previous_status=purchase.match_status,
        previous_confidence=purchase.match_confidence,
        new_status="tolerance",
        new_confidence=payload.confidence,
        reason=payload.reason,
        evidence={
            "invoice_no": purchase.invoice_no,
            "vendor_gstin": purchase.vendor_gstin,
            "matched_to_invoice_no": gstr2b.invoice_no if gstr2b else None,
        },
        created_by_user_id=user.id,
    )
    purchase.match_status = "tolerance"
    purchase.match_confidence = payload.confidence
    db.add(action)
    _refresh_result_counts(db, result)
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="reconciliation.manual_match",
        aggregate_type="transaction",
        aggregate_id=str(purchase.id),
        source_module="reconciliation",
        payload={"client_id": str(purchase.client_id), "reason": payload.reason, "confidence": payload.confidence},
    )
    db.commit()
    db.refresh(action)
    return _action_out(action)


@router.post("/unmatch")
def unmatch(payload: UnmatchRequest, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    purchase = _transaction_or_404(db, request.state.org_id, payload.purchase_transaction_id)
    if purchase.source != "upload":
        raise HTTPException(422, "purchase_transaction_id must refer to a purchase register transaction")
    result = None
    if payload.result_id:
        result = scoped(db, ReconciliationResult, request.state.org_id).filter(ReconciliationResult.id == payload.result_id).first()
        if not result:
            raise HTTPException(404, "Reconciliation result not found")
    action = ReconciliationMatchAction(
        org_id=request.state.org_id,
        client_id=purchase.client_id,
        result_id=result.id if result else None,
        purchase_transaction_id=purchase.id,
        action_type="unmatch",
        previous_status=purchase.match_status,
        previous_confidence=purchase.match_confidence,
        new_status="unmatched",
        new_confidence=None,
        reason=payload.reason,
        evidence={"invoice_no": purchase.invoice_no, "vendor_gstin": purchase.vendor_gstin},
        created_by_user_id=user.id,
    )
    purchase.match_status = "unmatched"
    purchase.match_confidence = None
    db.add(action)
    _refresh_result_counts(db, result)
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="reconciliation.unmatched",
        aggregate_type="transaction",
        aggregate_id=str(purchase.id),
        source_module="reconciliation",
        payload={"client_id": str(purchase.client_id), "reason": payload.reason},
    )
    db.commit()
    db.refresh(action)
    return _action_out(action)


@router.get("/actions")
def list_match_actions(request: Request, db: Session = Depends(get_db),
                       client_id: str | None = None,
                       transaction_id: str | None = None,
                       limit: int = 100,
                       _=Depends(get_current_user)):
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    query = scoped(db, ReconciliationMatchAction, request.state.org_id)
    if client_id:
        _client_or_404(db, request.state.org_id, client_id)
        query = query.filter(ReconciliationMatchAction.client_id == client_id)
    if transaction_id:
        query = query.filter(ReconciliationMatchAction.purchase_transaction_id == transaction_id)
    return [_action_out(row) for row in query.order_by(ReconciliationMatchAction.created_at.desc()).limit(limit).all()]


@router.post("/actions/{action_id}/rollback")
def rollback_action(action_id: str, request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    action = scoped(db, ReconciliationMatchAction, request.state.org_id).filter(ReconciliationMatchAction.id == action_id).first()
    if not action:
        raise HTTPException(404, "Reconciliation action not found")
    purchase = _transaction_or_404(db, request.state.org_id, str(action.purchase_transaction_id))
    result = scoped(db, ReconciliationResult, request.state.org_id).filter(ReconciliationResult.id == action.result_id).first() if action.result_id else None
    rollback = ReconciliationMatchAction(
        org_id=request.state.org_id,
        client_id=action.client_id,
        result_id=action.result_id,
        purchase_transaction_id=action.purchase_transaction_id,
        gstr2b_transaction_id=action.gstr2b_transaction_id,
        action_type="rollback",
        previous_status=purchase.match_status,
        previous_confidence=purchase.match_confidence,
        new_status=action.previous_status or "unmatched",
        new_confidence=action.previous_confidence,
        reason=f"Rollback of action {action.id}",
        evidence={"rolled_back_action_id": str(action.id), "rolled_back_action_type": action.action_type},
        created_by_user_id=user.id,
    )
    purchase.match_status = action.previous_status or "unmatched"
    purchase.match_confidence = action.previous_confidence
    db.add(rollback)
    _refresh_result_counts(db, result)
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="reconciliation.action_rolled_back",
        aggregate_type="transaction",
        aggregate_id=str(purchase.id),
        source_module="reconciliation",
        payload={"rolled_back_action_id": str(action.id), "new_status": purchase.match_status},
    )
    db.commit()
    db.refresh(rollback)
    return _action_out(rollback)


@router.get("/config/{client_id}", response_model=ReconciliationConfigOut)
def get_config(client_id: str, request: Request, db: Session = Depends(get_db),
               _=Depends(get_current_user)):
    _client_or_404(db, request.state.org_id, client_id)
    cfg = db.query(ReconciliationConfig).filter(
        ReconciliationConfig.client_id == client_id).first()
    if not cfg:
        # Return defaults
        return ReconciliationConfigOut(
            client_id=client_id, amount_tolerance=5,
            date_tolerance=3, fuzzy_threshold=85,
        )
    return cfg


@router.put("/config/{client_id}", response_model=ReconciliationConfigOut)
def update_config(client_id: str, req: ReconciliationConfigUpdate,
                  request: Request, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _client_or_404(db, request.state.org_id, client_id)
    cfg = db.query(ReconciliationConfig).filter(
        ReconciliationConfig.client_id == client_id).first()
    if not cfg:
        cfg = ReconciliationConfig(client_id=client_id)
        db.add(cfg)
    updates = req.model_dump(exclude_none=True)
    if not updates:
        return cfg
    for key, val in updates.items():
        setattr(cfg, key, val)
    log_activity(db, request.state.org_id, user.id, "reconciliation_config_update", client_id, 120, updates)
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="reconciliation.config.updated",
        aggregate_type="client",
        aggregate_id=client_id,
        source_module="reconciliation",
        payload={"changed_fields": sorted(updates.keys()), "config": updates},
    )
    db.commit()
    db.refresh(cfg)
    return cfg


@router.get("/export/{result_id}")
def export_excel(result_id: str, request: Request,
                 db: Session = Depends(get_db), user=Depends(get_current_user)):
    from app.utils.export_utils import build_reconciliation_excel

    result = (scoped(db, ReconciliationResult, request.state.org_id)
              .filter(ReconciliationResult.id == result_id).first())
    if not result:
        raise HTTPException(404, "Reconciliation result not found")
    if result.status != "completed":
        raise HTTPException(409, "Only completed reconciliation results can be exported")
    client = _client_or_404(db, request.state.org_id, str(result.client_id))

    matched_query = scoped(db, Transaction, request.state.org_id).filter(
        Transaction.client_id == result.client_id,
        Transaction.source == "upload",
        Transaction.match_status.in_(["exact", "tolerance", "fuzzy"]),
    )
    unmatched_query = scoped(db, Transaction, request.state.org_id).filter(
        Transaction.client_id == result.client_id,
        Transaction.source == "upload",
        Transaction.match_status == "unmatched",
    )
    from app.tasks.reconciliation_tasks import _period_bounds
    bounds = _period_bounds(result.period)
    if bounds:
        matched_query = matched_query.filter(Transaction.date.between(*bounds))
        unmatched_query = unmatched_query.filter(Transaction.date.between(*bounds))
    matched = matched_query.all()
    unmatched = unmatched_query.all()

    def to_row(r):
        return {
            "invoice_no": r.invoice_no, "vendor_name": r.vendor_name,
            "vendor_gstin": r.vendor_gstin, "amount": float(r.amount or 0),
            "date": r.date, "match_type": r.match_status,
            "confidence": float(r.match_confidence or 0),
            "source": r.source,
        }

    xlsx_bytes = build_reconciliation_excel(
        [to_row(r) for r in matched],
        [to_row(r) for r in unmatched],
        {
            "client_name": client.name,
            "period": result.period,
            "status": result.status,
            "total_purchase": float(result.total_purchase or 0),
            "total_gstr2b": float(result.total_gstr2b or 0),
            "matched_count": result.matched_count or 0,
            "unmatched_count": result.unmatched_count or 0,
            "mismatch_value": float(result.mismatch_value or 0),
            "run_at": result.run_at,
            "completed_at": result.completed_at,
        },
    )
    log_activity(db, request.state.org_id, user.id, "export", str(result.client_id), 300, {"type": "reconciliation"})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="reconciliation.exported",
        aggregate_type="reconciliation_result",
        aggregate_id=str(result.id),
        source_module="reconciliation",
        payload={"client_id": str(result.client_id), "period": result.period, "format": "xlsx"},
    )
    db.commit()
    safe_period = result.period.replace(" ", "-")
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="reconciliation_{safe_period}_{result_id}.xlsx"'},
    )
