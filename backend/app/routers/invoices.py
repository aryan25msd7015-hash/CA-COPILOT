from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.client import Client
from app.models.transaction import Transaction
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped

router = APIRouter()
FRAUD_STATUSES = {"open", "confirmed", "needs_followup", "false_positive", "cleared", "rescanning"}


class FraudReviewRequest(BaseModel):
    review_status: str = Field(default="confirmed", min_length=1, max_length=30)
    note: str | None = Field(default=None, max_length=1000)


def _txn_out(row: Transaction) -> dict:
    return {
        "id": str(row.id),
        "client_id": str(row.client_id),
        "client_name": row.client.name if row.client else None,
        "invoice_no": row.invoice_no,
        "vendor_name": row.vendor_name,
        "vendor_gstin": row.vendor_gstin,
        "amount": float(row.amount or 0),
        "tax_amount": float(row.tax_amount or 0) if row.tax_amount is not None else None,
        "date": row.date.isoformat() if row.date else None,
        "fraud_flag": row.fraud_flag,
        "fraud_review_status": row.fraud_review_status or ("open" if row.fraud_flag else "cleared"),
        "fraud_review_note": row.fraud_review_note,
        "fraud_reviewed_by_user_id": str(row.fraud_reviewed_by_user_id) if row.fraud_reviewed_by_user_id else None,
        "fraud_reviewed_at": row.fraud_reviewed_at.isoformat() if row.fraud_reviewed_at else None,
        "fraud_scanned_at": row.fraud_scanned_at.isoformat() if row.fraud_scanned_at else None,
        "match_status": row.match_status,
        "anomaly_score": float(row.anomaly_score or 0) if row.anomaly_score is not None else None,
    }


@router.get("/fraud-queue")
def fraud_queue(
    request: Request,
    db: Session = Depends(get_db),
    review_status: Optional[str] = None,
    client_id: Optional[str] = None,
    min_amount: Optional[float] = None,
    q: Optional[str] = None,
    include_cleared: bool = False,
    skip: int = 0,
    limit: int = 200,
    _=Depends(get_current_user),
):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    query = (
        scoped(db, Transaction, request.state.org_id)
        .options(joinedload(Transaction.client))
        .join(Client, Client.id == Transaction.client_id)
    )
    if include_cleared:
        query = query.filter(or_(Transaction.fraud_flag.isnot(None), Transaction.fraud_review_status == "cleared"))
    else:
        query = query.filter(Transaction.fraud_flag.isnot(None))
    if review_status:
        allowed = {item.strip() for item in review_status.split(",") if item.strip()}
        if not allowed.issubset(FRAUD_STATUSES):
            raise HTTPException(422, "Invalid review_status")
        query = query.filter(Transaction.fraud_review_status.in_(allowed))
    if client_id:
        query = query.filter(Transaction.client_id == client_id)
    if min_amount is not None:
        if min_amount < 0:
            raise HTTPException(422, "min_amount must be >= 0")
        query = query.filter(Transaction.amount >= min_amount)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(
            Client.name.ilike(term),
            Transaction.invoice_no.ilike(term),
            Transaction.vendor_name.ilike(term),
            Transaction.vendor_gstin.ilike(term),
            Transaction.fraud_flag.ilike(term),
        ))
    rows = query.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return [_txn_out(row) for row in rows]


@router.get("/fraud-summary")
def fraud_summary(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = (
        scoped(db, Transaction, request.state.org_id)
        .with_entities(Transaction.fraud_review_status, func.count(Transaction.id), func.sum(Transaction.amount))
        .filter(or_(Transaction.fraud_flag.isnot(None), Transaction.fraud_review_status == "cleared"))
        .group_by(Transaction.fraud_review_status)
        .all()
    )
    result = {status: {"count": int(count), "amount": float(amount or 0)} for status, count, amount in rows}
    return {status: result.get(status, {"count": 0, "amount": 0}) for status in FRAUD_STATUSES}


@router.post("/{transaction_id}/rescan")
def rescan(transaction_id: str, request: Request, db: Session = Depends(get_db),
           user=Depends(require_role(["partner", "manager"]))):
    txn = scoped(db, Transaction, request.state.org_id).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    if not (txn.invoice_no or txn.vendor_gstin or txn.fingerprint):
        raise HTTPException(409, "Transaction does not contain enough invoice data to rescan")
    from app.tasks.anomaly_tasks import run_invoice_fraud_scan

    task = run_invoice_fraud_scan.delay(str(txn.id))
    txn.fraud_scanned_at = datetime.now(timezone.utc)
    txn.fraud_review_status = "rescanning"
    txn.fraud_review_note = "Rescan requested"
    txn.fraud_reviewed_by_user_id = user.id
    txn.fraud_reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(txn)
    return {"task_id": task.id, "invoice": _txn_out(txn)}


@router.get("/{transaction_id}/fraud-status")
def fraud_status(transaction_id: str, request: Request, db: Session = Depends(get_db),
                 _=Depends(get_current_user)):
    txn = (
        scoped(db, Transaction, request.state.org_id)
        .options(joinedload(Transaction.client))
        .filter(Transaction.id == transaction_id)
        .first()
    )
    if not txn:
        raise HTTPException(404, "Transaction not found")
    return _txn_out(txn)


@router.patch("/{transaction_id}/review")
def review_flag(transaction_id: str, payload: FraudReviewRequest, request: Request,
                db: Session = Depends(get_db), user=Depends(require_role(["partner", "manager"]))):
    txn = scoped(db, Transaction, request.state.org_id).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    review_status = payload.review_status.strip()
    if review_status not in FRAUD_STATUSES:
        raise HTTPException(422, "Invalid review_status")
    if review_status != "cleared" and not txn.fraud_flag:
        raise HTTPException(409, "Transaction has no fraud flag")
    txn.fraud_review_status = review_status
    txn.fraud_review_note = payload.note.strip() if payload.note else None
    txn.fraud_reviewed_by_user_id = user.id
    txn.fraud_reviewed_at = datetime.now(timezone.utc)
    if review_status in {"false_positive", "cleared"}:
        txn.fraud_flag = None
    db.commit()
    db.refresh(txn)
    return _txn_out(txn)


@router.patch("/{transaction_id}/clear-flag")
def clear_flag(transaction_id: str, request: Request, db: Session = Depends(get_db),
               user=Depends(require_role(["partner"]))):
    txn = scoped(db, Transaction, request.state.org_id).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise HTTPException(404, "Transaction not found")
    txn.fraud_flag = None
    txn.fraud_review_status = "cleared"
    txn.fraud_review_note = "Flag cleared by partner"
    txn.fraud_reviewed_by_user_id = user.id
    txn.fraud_reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return _txn_out(txn)
