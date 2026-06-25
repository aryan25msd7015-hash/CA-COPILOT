from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.system import SystemEvent
from app.utils.deps import get_current_user, require_role
from app.utils.events import mark_event_dispatched, mark_event_failed
from app.utils.scoped_query import scoped

router = APIRouter()


def _event_out(row: SystemEvent) -> dict:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "aggregate_type": row.aggregate_type,
        "aggregate_id": row.aggregate_id,
        "source_module": row.source_module,
        "status": row.status,
        "correlation_id": row.correlation_id,
        "causation_id": row.causation_id,
        "payload": row.payload,
        "dispatch_attempts": row.dispatch_attempts,
        "last_error": row.last_error,
        "dispatched_at": row.dispatched_at,
        "created_at": row.created_at,
    }


@router.get("")
def list_events(
    request: Request,
    db: Session = Depends(get_db),
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    aggregate_type: Optional[str] = None,
    aggregate_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    _=Depends(get_current_user),
):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 500:
        raise HTTPException(422, "limit must be between 1 and 500")
    query = scoped(db, SystemEvent, request.state.org_id)
    if event_type:
        query = query.filter(SystemEvent.event_type == event_type)
    if status:
        query = query.filter(SystemEvent.status == status)
    if aggregate_type:
        query = query.filter(SystemEvent.aggregate_type == aggregate_type)
    if aggregate_id:
        query = query.filter(SystemEvent.aggregate_id == aggregate_id)
    return [_event_out(row) for row in query.order_by(SystemEvent.created_at.desc()).offset(skip).limit(limit).all()]


@router.get("/summary")
def event_summary(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = scoped(db, SystemEvent, request.state.org_id).all()
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for row in rows:
        by_status[row.status] = by_status.get(row.status, 0) + 1
        by_type[row.event_type] = by_type.get(row.event_type, 0) + 1
    return {
        "organization_id": str(request.state.org_id),
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "total_events": len(rows),
        "by_status": by_status,
        "by_type": by_type,
    }


@router.post("/{event_id}/dispatch")
def dispatch_event(event_id: str, request: Request, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    row = scoped(db, SystemEvent, request.state.org_id).filter(SystemEvent.id == event_id).first()
    if not row:
        raise HTTPException(404, "Event not found")
    try:
        mark_event_dispatched(db, row)
    except Exception as exc:
        mark_event_failed(db, row, str(exc))
    db.commit()
    db.refresh(row)
    return _event_out(row)
