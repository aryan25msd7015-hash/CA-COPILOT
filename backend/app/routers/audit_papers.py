import io
import base64
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import get_db
from app.models.document import Document
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped
from app.utils.activity import log_activity

router = APIRouter()


class AuditRequest(BaseModel):
    document_id: str
    period: str = "Current period"

    @field_validator("period")
    @classmethod
    def valid_period(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or len(normalized) > 80:
            raise ValueError("Invalid audit period")
        return normalized


def _valid_task_id(task_id: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{8,80}", task_id))


def _audit_status(doc: Document) -> dict:
    ocr_json = doc.ocr_json or {}
    audit_status = ocr_json.get("audit_status")
    if ocr_json.get("audit_result"):
        audit_status = "ready"
    elif doc.celery_task_id and audit_status not in {"failed", "ready"}:
        audit_status = audit_status or "queued"
    else:
        audit_status = audit_status or "ready_to_generate"
    return {
        "id": str(doc.id),
        "client_id": str(doc.client_id),
        "document_status": doc.status,
        "audit_status": audit_status,
        "task_id": doc.celery_task_id,
        "audit_started_at": ocr_json.get("audit_started_at"),
        "audit_completed_at": ocr_json.get("audit_completed_at"),
        "audit_error": ocr_json.get("audit_error"),
        "audit_result": ocr_json.get("audit_result"),
    }


@router.post("/generate")
def generate(payload: AuditRequest, request: Request, db: Session = Depends(get_db),
             user=Depends(get_current_user)):
    doc = scoped(db, Document, request.state.org_id).filter(
        Document.id == payload.document_id, Document.doc_type == "trial_balance"
    ).first()
    if not doc:
        raise HTTPException(404, "Trial balance document not found")
    if not doc.s3_key:
        raise HTTPException(409, "Trial balance source file is missing")
    if doc.celery_task_id and not (doc.ocr_json or {}).get("audit_result"):
        raise HTTPException(409, "Audit paper generation is already queued")
    from app.tasks.llm_tasks import generate_audit_papers

    task = generate_audit_papers.delay(str(doc.id), payload.period)
    doc.celery_task_id = task.id
    doc.ocr_json = {
        **(doc.ocr_json or {}),
        "audit_status": "queued",
        "audit_error": None,
        "audit_queued_at": datetime.now(timezone.utc).isoformat(),
    }
    log_activity(db, request.state.org_id, user.id, "document_review", str(doc.client_id), 1800, {"type": "audit_paper"})
    db.commit()
    return {"task_id": task.id, "audit": _audit_status(doc)}


@router.get("/document/{document_id}")
def get_audit_document(document_id: str, request: Request, db: Session = Depends(get_db),
                       _=Depends(get_current_user)):
    doc = scoped(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.doc_type != "trial_balance":
        raise HTTPException(400, "Document is not a trial balance")
    return (doc.ocr_json or {}).get("audit_result", {})


@router.get("/export/{document_id}")
def export_audit(document_id: str, request: Request, db: Session = Depends(get_db),
                 _=Depends(get_current_user)):
    from app.services.s3_service import download_bytes

    doc = scoped(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.doc_type != "trial_balance":
        raise HTTPException(400, "Document is not a trial balance")
    result = (doc.ocr_json or {}).get("audit_result", {}) if doc else {}
    if not result.get("s3_key") and not result.get("docx_base64"):
        raise HTTPException(404, "Generated working paper not found")
    if result.get("docx_base64"):
        payload = base64.b64decode(result["docx_base64"])
    else:
        payload = download_bytes(result["s3_key"])
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="audit-paper-{document_id}.docx"'},
    )


@router.get("/document/{document_id}/status")
def get_audit_document_status(document_id: str, request: Request, db: Session = Depends(get_db),
                              _=Depends(get_current_user)):
    doc = scoped(db, Document, request.state.org_id).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.doc_type != "trial_balance":
        raise HTTPException(400, "Document is not a trial balance")
    response = _audit_status(doc)
    if doc.celery_task_id:
        task = celery_app.AsyncResult(doc.celery_task_id)
        response["task_state"] = task.state
        if task.state == "FAILURE":
            response["task_error"] = str(task.result)
    return response


@router.get("/{task_id}")
def get_audit_status(task_id: str, _=Depends(get_current_user)):
    if not _valid_task_id(task_id):
        raise HTTPException(422, "Invalid task id")
    result = celery_app.AsyncResult(task_id)
    response = {"state": result.state, "task_id": task_id}
    if result.state == "SUCCESS":
        response["result"] = result.result
    elif result.state == "FAILURE":
        response["error"] = str(result.result)
    return response
