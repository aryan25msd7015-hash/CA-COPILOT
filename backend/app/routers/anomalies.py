from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from typing import Optional

from app.database import get_db
from app.models.anomaly_flag import AnomalyFlag
from app.models.client import Client
from app.models.transaction import Transaction
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped

router = APIRouter()
REVIEW_STATUSES = {"open", "confirmed", "false_positive", "needs_followup"}


class AnomalyReviewRequest(BaseModel):
    review_status: str = Field(default="confirmed", min_length=1, max_length=30)
    note: str | None = Field(default=None, max_length=1000)


@router.get("")
def list_anomalies(request: Request, db: Session = Depends(get_db),
                   reviewed: Optional[bool] = None,
                   review_status: Optional[str] = None,
                   client_id: Optional[str] = None,
                   flag_type: Optional[str] = None,
                   min_risk: Optional[float] = None,
                   q: Optional[str] = None,
                   skip: int = 0, limit: int = 200,
                   _=Depends(get_current_user)):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    query = (
        scoped(db, AnomalyFlag, request.state.org_id)
        .options(joinedload(AnomalyFlag.client), joinedload(AnomalyFlag.transaction))
        .join(Client, Client.id == AnomalyFlag.client_id)
    )
    if reviewed is not None:
        query = query.filter(AnomalyFlag.reviewed.is_(reviewed))
    if review_status:
        allowed = {item.strip() for item in review_status.split(",") if item.strip()}
        if not allowed.issubset(REVIEW_STATUSES):
            raise HTTPException(422, "Invalid review_status")
        query = query.filter(AnomalyFlag.review_status.in_(allowed))
    if client_id:
        query = query.filter(AnomalyFlag.client_id == client_id)
    if flag_type:
        if len(flag_type) > 30:
            raise HTTPException(422, "Invalid flag_type")
        query = query.filter(AnomalyFlag.flag_type == flag_type)
    if min_risk is not None:
        if min_risk < 0 or min_risk > 1:
            raise HTTPException(422, "min_risk must be between 0 and 1")
        query = query.filter(AnomalyFlag.risk_score >= min_risk)
    if q:
        term = f"%{q.strip()}%"
        query = query.outerjoin(Transaction, Transaction.id == AnomalyFlag.transaction_id).filter(or_(
            Client.name.ilike(term),
            AnomalyFlag.flag_type.ilike(term),
            Transaction.invoice_no.ilike(term),
            Transaction.vendor_name.ilike(term),
            Transaction.vendor_gstin.ilike(term),
        ))
    flags = query.order_by(AnomalyFlag.risk_score.desc()).offset(skip).limit(limit).all()
    return [_flag_out(f) for f in flags]


@router.get("/summary")
def anomaly_summary(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = (
        scoped(db, AnomalyFlag, request.state.org_id)
        .with_entities(AnomalyFlag.review_status, func.count(AnomalyFlag.id), func.max(AnomalyFlag.risk_score))
        .group_by(AnomalyFlag.review_status)
        .all()
    )
    by_status = {status or "open": {"count": int(count), "max_risk": float(max_risk or 0)} for status, count, max_risk in rows}
    return {
        "total": sum(item["count"] for item in by_status.values()),
        "open": by_status.get("open", {"count": 0, "max_risk": 0}),
        "confirmed": by_status.get("confirmed", {"count": 0, "max_risk": 0}),
        "false_positive": by_status.get("false_positive", {"count": 0, "max_risk": 0}),
        "needs_followup": by_status.get("needs_followup", {"count": 0, "max_risk": 0}),
    }


@router.get("/client/{client_id}")
def client_anomalies(client_id: str, request: Request,
                     db: Session = Depends(get_db),
                     flag_type: Optional[str] = None, reviewed: Optional[bool] = None,
                     skip: int = 0, limit: int = 200,
                     _=Depends(get_current_user)):
    # Verify client in org
    client = (scoped(db, Client, request.state.org_id)
              .filter(Client.id == client_id).first())
    if not client:
        raise HTTPException(404, "Client not found")
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    q = scoped(db, AnomalyFlag, request.state.org_id).filter(AnomalyFlag.client_id == client_id)
    if flag_type:
        if len(flag_type) > 30:
            raise HTTPException(422, "Invalid flag_type")
        q = q.filter(AnomalyFlag.flag_type == flag_type)
    if reviewed is not None:
        q = q.filter(AnomalyFlag.reviewed.is_(reviewed))
    flags = q.order_by(AnomalyFlag.risk_score.desc()).offset(skip).limit(limit).all()
    return [_flag_out(f) for f in flags]


@router.patch("/{flag_id}/review")
def mark_reviewed(flag_id: str, request: Request,
                  payload: AnomalyReviewRequest | None = None,
                  db: Session = Depends(get_db), user=Depends(get_current_user)):
    flag = (scoped(db, AnomalyFlag, request.state.org_id)
            .filter(AnomalyFlag.id == flag_id).first())
    if not flag:
        raise HTTPException(404, "Flag not found")
    review_status = (payload.review_status if payload else "confirmed").strip()
    if review_status not in REVIEW_STATUSES:
        raise HTTPException(422, "Invalid review_status")
    flag.review_status = review_status
    flag.review_note = payload.note.strip() if payload and payload.note else None
    flag.reviewed = review_status != "open"
    flag.reviewed_by_user_id = user.id if flag.reviewed else None
    flag.reviewed_at = datetime.now(timezone.utc) if flag.reviewed else None
    db.commit()
    db.refresh(flag)
    return _flag_out(flag)


def _flag_out(f: AnomalyFlag) -> dict:
    return {
        "id": str(f.id), "client_id": str(f.client_id),
        "client_name": f.client.name if f.client else None,
        "transaction_id": str(f.transaction_id) if f.transaction_id else None,
        "transaction": {
            "invoice_no": f.transaction.invoice_no,
            "vendor_name": f.transaction.vendor_name,
            "vendor_gstin": f.transaction.vendor_gstin,
            "amount": float(f.transaction.amount or 0) if f.transaction.amount is not None else None,
            "tax_amount": float(f.transaction.tax_amount or 0) if f.transaction.tax_amount is not None else None,
            "date": f.transaction.date.isoformat() if f.transaction.date else None,
            "match_status": f.transaction.match_status,
        } if f.transaction else None,
        "flag_type": f.flag_type, "risk_score": float(f.risk_score or 0),
        "details": f.details, "reviewed": f.reviewed,
        "review_status": f.review_status or ("confirmed" if f.reviewed else "open"),
        "review_note": f.review_note,
        "reviewed_by_user_id": str(f.reviewed_by_user_id) if f.reviewed_by_user_id else None,
        "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
        "created_at": f.created_at.isoformat(),
    }
