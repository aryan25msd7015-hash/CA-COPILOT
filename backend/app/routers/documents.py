import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from botocore.exceptions import BotoCoreError, ClientError
from typing import List, Optional

from app.database import get_db
from app.config import settings
from app.models.document import Document
from app.models.client import Client
from app.schemas.document import UploadUrlRequest, UploadUrlResponse, DocumentOut
from app.services.s3_service import generate_presigned_put_url
from app.utils.deps import get_current_user
from app.utils.scoped_query import scoped
from app.utils.activity import log_activity
from app.utils.events import publish_event

router = APIRouter()

VALID_DOC_TYPES = {
    "invoice", "gstr2b", "purchase_register",
    "notice", "trial_balance", "bank_statement", "udyam_certificate",
    "inventory_ledger", "debtor_ledger", "balance_sheet", "pnl", "itr",
    "gstr9", "lease_agreement", "rfp", "board_transcript",
}
VALID_STATUSES = {
    "pending_upload",
    "received",
    "pending",
    "processing",
    "ocr_complete",
    "ocr_failed",
    "parse_failed",
    "failed_validation",
    "verified",
    "processed",
}
VALID_EXTENSIONS = {
    "pdf", "xlsx", "xls", "csv", "json", "jpg", "jpeg", "png",
}
DOC_TYPE_EXTENSIONS = {
    "gstr2b": {"json", "csv", "xlsx", "xls"},
    "purchase_register": {"csv", "xlsx", "xls"},
}
CONTENT_TYPE_MAP = {
    "pdf": "application/pdf",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "csv": "text/csv",
    "json": "application/json",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
}
ALLOWED_UPLOAD_MIMES = {
    "application/pdf": 50 * 1024 * 1024,
    "image/jpeg": 10 * 1024 * 1024,
    "image/png": 10 * 1024 * 1024,
    "text/csv": 10 * 1024 * 1024,
    "application/json": 10 * 1024 * 1024,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": 25 * 1024 * 1024,
    "application/vnd.ms-excel": 25 * 1024 * 1024,
}


def _extension(filename: str | None) -> str:
    if not filename:
        return "pdf"
    parts = filename.rsplit(".", 1)
    if len(parts) != 2 or not parts[1]:
        raise HTTPException(422, "Filename must include a supported extension")
    ext = parts[1].lower()
    if ext not in VALID_EXTENSIONS:
        raise HTTPException(422, f"Unsupported file extension: {ext}")
    return ext


def _validate_doc_file(doc_type: str, ext: str) -> None:
    allowed = DOC_TYPE_EXTENSIONS.get(doc_type)
    if allowed and ext not in allowed:
        raise HTTPException(422, f"{doc_type} uploads must use one of: {sorted(allowed)}")


def _validate_upload_metadata(req: UploadUrlRequest, content_type: str) -> None:
    mime_type = req.mime_type or content_type
    if mime_type != content_type:
        raise HTTPException(422, "MIME type does not match file extension")
    max_size = ALLOWED_UPLOAD_MIMES.get(mime_type)
    if not max_size:
        raise HTTPException(422, f"MIME type '{mime_type}' is not allowed")
    if req.file_size_bytes is not None:
        if req.file_size_bytes <= 0:
            raise HTTPException(422, "file_size_bytes must be greater than zero")
        if req.file_size_bytes > max_size:
            raise HTTPException(413, f"File exceeds maximum size for {mime_type}")


@router.post("/upload-url", response_model=UploadUrlResponse, status_code=201)
def get_upload_url(req: UploadUrlRequest, request: Request,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    if req.doc_type not in VALID_DOC_TYPES:
        raise HTTPException(400, f"Invalid doc_type. Must be one of: {VALID_DOC_TYPES}")
    client = (scoped(db, Client, request.state.org_id)
              .filter(Client.id == req.client_id).first())
    if not client:
        raise HTTPException(404, "Client not found")

    ext = _extension(req.filename)
    _validate_doc_file(req.doc_type, ext)

    content_type = CONTENT_TYPE_MAP[ext]
    _validate_upload_metadata(req, content_type)
    key = f"tenants/{request.state.org_id}/clients/{req.client_id}/source_docs/{uuid.uuid4()}.{ext}"
    expires_in = 300
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    doc = Document(
        org_id=request.state.org_id,
        client_id=req.client_id,
        doc_type=req.doc_type,
        s3_key=key,
        original_filename=req.filename,
        file_size_bytes=str(req.file_size_bytes) if req.file_size_bytes is not None else None,
        mime_type=content_type,
        uploaded_by_user_id=user.id,
        upload_expires_at=expires_at,
        source="upload",
        status="pending_upload",
    )
    db.add(doc)
    log_activity(db, request.state.org_id, user.id, "upload", req.client_id, 300, {"doc_type": req.doc_type})
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=user.id,
        event_type="document.upload_url.generated",
        aggregate_type="document",
        aggregate_id=str(doc.id),
        source_module="documents",
        payload={"client_id": req.client_id, "doc_type": req.doc_type, "mime_type": content_type, "expires_at": expires_at.isoformat()},
    )
    db.commit()
    db.refresh(doc)
    try:
        upload_url = generate_presigned_put_url(key, content_type=content_type, expires=expires_in)
    except (BotoCoreError, ClientError) as exc:
        if settings.ENV == "production":
            raise HTTPException(503, f"Storage upload URL unavailable: {exc}") from exc
        upload_url = f"http://localhost:8000/documents/local-upload/{doc.id}"

    return UploadUrlResponse(
        upload_url=upload_url,
        document_id=str(doc.id),
        s3_key=key,
        content_type=content_type,
        expires_in_seconds=expires_in,
        upload_status="pending_upload",
    )


@router.put("/local-upload/{document_id}")
async def local_upload(document_id: str, request: Request, db: Session = Depends(get_db)):
    """Development-only direct upload sink used when cloud credentials are unavailable."""
    if settings.ENV == "production":
        raise HTTPException(404, "Not found")
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    body = await request.body()
    if doc.file_size_bytes and len(body) > int(doc.file_size_bytes):
        raise HTTPException(413, "Uploaded file exceeds signed size")
    doc.status = "received"
    doc.received_at = datetime.now(timezone.utc)
    publish_event(
        db,
        org_id=doc.org_id,
        event_type="document.received",
        aggregate_type="document",
        aggregate_id=str(doc.id),
        source_module="documents",
        payload={"client_id": str(doc.client_id), "bytes": len(body), "source": "local_upload"},
    )
    db.commit()
    return {"detail": "received", "document_id": document_id, "bytes": len(body)}


@router.post("/{document_id}/process")
def process_document(document_id: str, request: Request,
                     db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Start OCR after a direct-to-S3 upload has completed."""
    doc = (scoped(db, Document, request.state.org_id)
           .filter(Document.id == document_id).first())
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.status in {"processed", "ocr_complete"}:
        raise HTTPException(409, f"Document is already {doc.status}")
    if doc.status == "pending_upload":
        expires_at = doc.upload_expires_at
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at and expires_at < datetime.now(timezone.utc):
            raise HTTPException(409, "Upload URL expired before upload confirmation")
        doc.status = "received"
        doc.received_at = datetime.now(timezone.utc)
    if doc.status == "pending" and doc.celery_task_id:
        raise HTTPException(409, "Document processing is already queued")
    from app.tasks.ocr_tasks import run_ocr
    task = run_ocr.delay(str(doc.id))
    doc.celery_task_id = task.id
    doc.status = "pending"
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=request.state.user_id,
        event_type="document.ocr.queued",
        aggregate_type="document",
        aggregate_id=str(doc.id),
        source_module="documents",
        payload={"client_id": str(doc.client_id), "task_id": task.id, "doc_type": doc.doc_type},
    )
    db.commit()
    return {"task_id": task.id}


@router.get("", response_model=List[DocumentOut])
def list_documents(request: Request, db: Session = Depends(get_db),
                   client_id: Optional[str] = None,
                   doc_type: Optional[str] = None,
                   status: Optional[str] = None,
                   skip: int = 0, limit: int = 50,
                   _=Depends(get_current_user)):
    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    q = scoped(db, Document, request.state.org_id)
    if client_id:
        client = scoped(db, Client, request.state.org_id).filter(Client.id == client_id).first()
        if not client:
            raise HTTPException(404, "Client not found")
        q = q.filter(Document.client_id == client_id)
    if doc_type:
        if doc_type not in VALID_DOC_TYPES:
            raise HTTPException(422, "Invalid doc_type")
        q = q.filter(Document.doc_type == doc_type)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(422, "Invalid document status")
        q = q.filter(Document.status == status)
    return q.order_by(Document.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, request: Request,
                 db: Session = Depends(get_db), _=Depends(get_current_user)):
    doc = (scoped(db, Document, request.state.org_id)
           .filter(Document.id == document_id).first())
    if not doc:
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{document_id}/pipeline")
def get_document_pipeline(document_id: str, request: Request,
                          db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.document import DocumentExtraction, DocumentPipelineEvent

    doc = (scoped(db, Document, request.state.org_id)
           .filter(Document.id == document_id).first())
    if not doc:
        raise HTTPException(404, "Document not found")
    extractions = (
        scoped(db, DocumentExtraction, request.state.org_id)
        .filter(DocumentExtraction.document_id == document_id)
        .order_by(DocumentExtraction.created_at.desc())
        .all()
    )
    events = (
        scoped(db, DocumentPipelineEvent, request.state.org_id)
        .filter(DocumentPipelineEvent.document_id == document_id)
        .order_by(DocumentPipelineEvent.created_at.asc())
        .all()
    )
    return {
        "document_id": document_id,
        "status": doc.status,
        "last_pipeline_error_type": doc.last_pipeline_error_type,
        "extractions": [
            {
                "id": str(row.id),
                "supplier_name": row.supplier_name,
                "supplier_gstin": row.supplier_gstin,
                "invoice_number": row.invoice_number,
                "invoice_date": row.invoice_date,
                "taxable_value": row.taxable_value,
                "total_amount": row.total_amount,
                "confidence_score": row.confidence_score,
                "validation_status": row.validation_status,
                "validation_errors": row.validation_errors,
                "auto_tags": row.auto_tags,
                "created_at": row.created_at,
            }
            for row in extractions
        ],
        "events": [
            {
                "id": str(row.id),
                "stage": row.stage,
                "status": row.status,
                "error_type": row.error_type,
                "diagnostic_payload": row.diagnostic_payload,
                "created_at": row.created_at,
            }
            for row in events
        ],
    }


@router.post("/{document_id}/retry-ocr")
def retry_ocr(document_id: str, request: Request,
              db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.document import DocumentPipelineEvent

    doc = (scoped(db, Document, request.state.org_id)
           .filter(Document.id == document_id).first())
    if not doc:
        raise HTTPException(404, "Document not found")
    retryable_statuses = {"ocr_failed", "parse_failed", "failed_validation"}
    if doc.status not in retryable_statuses:
        raise HTTPException(409, f"Only {sorted(retryable_statuses)} documents can be retried")
    try:
        from app.tasks.ocr_tasks import run_ocr
        task = run_ocr.delay(str(doc.id))
        db.add(DocumentPipelineEvent(
            org_id=doc.org_id,
            client_id=doc.client_id,
            document_id=doc.id,
            stage="retry",
            status="queued",
            diagnostic_payload={
                "previous_status": doc.status,
                "previous_error_type": doc.last_pipeline_error_type,
            },
        ))
        doc.celery_task_id = task.id
        doc.status = "pending"
        doc.processing_started_at = None
        doc.processing_completed_at = None
        doc.last_pipeline_error_type = None
        publish_event(
            db,
            org_id=request.state.org_id,
            actor_id=request.state.user_id,
            event_type="document.ocr.retry_queued",
            aggregate_type="document",
            aggregate_id=str(doc.id),
            source_module="documents",
            payload={"client_id": str(doc.client_id), "task_id": task.id},
        )
        db.commit()
        return {"task_id": task.id, "message": "OCR re-queued", "status": doc.status}
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Failed to enqueue OCR: {e}")
