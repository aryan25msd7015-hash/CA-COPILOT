from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload
import re

from app.celery_app import celery_app
from app.database import get_db
from app.models.client import Client
from app.models.document import Document
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped
from app.utils.activity import log_activity

router = APIRouter()


class NoticeDraftRequest(BaseModel):
    document_id: str


def _valid_task_id(task_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", task_id))


def _notice_status(doc: Document) -> dict:
    ocr_json = doc.ocr_json or {}
    draft_status = ocr_json.get("draft_status")
    if ocr_json.get("draft_result"):
        draft_status = "ready"
    elif doc.celery_task_id and draft_status not in {"failed", "ready"}:
        draft_status = draft_status or "queued"
    elif doc.status in {"ocr_complete", "processed"} and doc.ocr_text:
        draft_status = draft_status or "ready_to_draft"
    else:
        draft_status = draft_status or "waiting_for_ocr"
    return {
        "id": str(doc.id),
        "client_id": str(doc.client_id),
        "client_name": doc.client.name if doc.client else None,
        "document_status": doc.status,
        "draft_status": draft_status,
        "task_id": doc.celery_task_id,
        "notice_data": ocr_json.get("notice_data"),
        "draft_result": ocr_json.get("draft_result"),
        "draft_error": ocr_json.get("draft_error"),
        "draft_queued_at": ocr_json.get("draft_queued_at"),
        "draft_started_at": ocr_json.get("draft_started_at"),
        "draft_completed_at": ocr_json.get("draft_completed_at"),
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
        "original_filename": doc.original_filename,
        "file_size_bytes": doc.file_size_bytes,
        "mime_type": doc.mime_type,
    }


@router.post("/draft")
def create_draft(payload: NoticeDraftRequest, request: Request, db: Session = Depends(get_db),
                 user=Depends(get_current_user)):
    doc = scoped(db, Document, request.state.org_id).filter(
        Document.id == payload.document_id, Document.doc_type == "notice"
    ).first()
    if not doc:
        raise HTTPException(404, "Notice document not found")
    if doc.status not in {"ocr_complete", "processed"} or not doc.ocr_text:
        raise HTTPException(409, "Notice OCR text is required before drafting")
    if doc.celery_task_id and not (doc.ocr_json or {}).get("draft_result"):
        raise HTTPException(409, "Notice draft is already queued")
    from app.tasks.llm_tasks import generate_notice_draft

    task = generate_notice_draft.delay(str(doc.id))
    doc.celery_task_id = task.id
    doc.ocr_json = {
        **(doc.ocr_json or {}),
        "draft_status": "queued",
        "draft_error": None,
        "draft_queued_at": datetime.now(timezone.utc).isoformat(),
    }
    log_activity(db, request.state.org_id, user.id, "notice_draft", str(doc.client_id), 1200)
    db.commit()
    return {"task_id": task.id, "notice": _notice_status(doc)}


@router.get("/draft/{task_id}")
def get_draft_status(task_id: str, _=Depends(get_current_user)):
    if not _valid_task_id(task_id):
        raise HTTPException(422, "Invalid task id")
    result = celery_app.AsyncResult(task_id)
    response = {"state": result.state, "task_id": task_id}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response


@router.get("")
def list_notices(request: Request, db: Session = Depends(get_db), skip: int = 0, limit: int = 2000,
                 draft_status: str | None = None,
                 client_id: str | None = None,
                 q: str | None = None,
                 notice_type: str | None = None,
                 section: str | None = None,
                 _=Depends(get_current_user)):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    query = (
        scoped(db, Document, request.state.org_id)
        .options(joinedload(Document.client))
        .join(Client, Client.id == Document.client_id)
        .filter(Document.doc_type == "notice")
    )
    if client_id:
        query = query.filter(Document.client_id == client_id)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(
            Client.name.ilike(term),
            Document.original_filename.ilike(term),
            Document.ocr_text.ilike(term),
        ))
    docs = query.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()
    rows = [_notice_status(doc) for doc in docs]
    if draft_status:
        allowed = {item.strip() for item in draft_status.split(",") if item.strip()}
        rows = [row for row in rows if row["draft_status"] in allowed]
    if notice_type:
        rows = [row for row in rows if (row.get("notice_data") or {}).get("notice_type") == notice_type]
    if section:
        rows = [row for row in rows if (row.get("notice_data") or {}).get("section") == section]
    return rows


@router.get("/{document_id}/status")
def get_notice_status(document_id: str, request: Request, db: Session = Depends(get_db),
                      _=Depends(get_current_user)):
    doc = scoped(db, Document, request.state.org_id).filter(
        Document.id == document_id,
        Document.doc_type == "notice",
    ).first()
    if not doc:
        raise HTTPException(404, "Notice document not found")
    response = _notice_status(doc)
    if doc.celery_task_id:
        task = celery_app.AsyncResult(doc.celery_task_id)
        response["task_state"] = task.state
        if task.state == "FAILURE":
            response["task_error"] = str(task.result)
    return response
