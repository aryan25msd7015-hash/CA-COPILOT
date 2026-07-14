"""WhatsApp pipeline Celery tasks - queue: whatsapp."""
import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.celery_app import celery_app
from app.database import SessionLocal

logger = logging.getLogger(__name__)

STOP_WORDS = {"STOP", "UNSUBSCRIBE", "CANCEL", "OPTOUT", "OPT OUT"}
START_WORDS = {"START", "YES", "Y", "OPTIN", "OPT IN", "SUBSCRIBE"}


def _digits(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _phone_candidates(raw_phone: str | None) -> list[str]:
    digits = _digits(raw_phone)
    candidates = {raw_phone or "", digits}
    if digits:
        candidates.add(f"+{digits}")
    if len(digits) == 10:
        candidates.update({f"91{digits}", f"+91{digits}"})
    if len(digits) == 12 and digits.startswith("91"):
        local = digits[-10:]
        candidates.update({local, f"+91{local}"})
    return [candidate for candidate in candidates if candidate]


def _find_client_by_phone(db, raw_phone: str | None):
    from app.models.client import Client

    candidates = _phone_candidates(raw_phone)
    client = db.query(Client).filter(Client.whatsapp_number.in_(candidates)).first()
    if client:
        return client

    raw_digits = _digits(raw_phone)
    if len(raw_digits) < 10:
        return None

    suffix = raw_digits[-10:]
    possible_clients = db.query(Client).filter(Client.whatsapp_number.isnot(None)).all()
    for possible_client in possible_clients:
        if _digits(possible_client.whatsapp_number).endswith(suffix):
            return possible_client
    return None


def _safe_send_text(phone: str, body: str) -> dict[str, Any]:
    from app.config import settings
    from app.services.whatsapp_service import send_text

    if not settings.WHATSAPP_TOKEN or not settings.WHATSAPP_PHONE_ID:
        logger.info("WhatsApp dev fallback reply to %s: %s", phone, body)
        return {"mode": "development_fallback", "to": phone}

    try:
        return send_text(phone, body)
    except Exception as exc:
        logger.warning("WhatsApp text reply failed for %s: %s", phone, exc)
        return {"mode": "failed", "error": str(exc)}


def _iter_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for message in value.get("messages") or []:
                if isinstance(message, dict):
                    messages.append(message)
    return messages


def _detect_doc_type(filename: str) -> str:
    name = filename.lower()
    if "gstr2b" in name or "gstr-2b" in name:
        return "gstr2b"
    if "purchase" in name:
        return "purchase_register"
    if "bank" in name:
        return "bank_statement"
    if "notice" in name:
        return "notice"
    return "invoice"


@celery_app.task(queue="whatsapp")
def morning_reminder_check():
    """Run daily at 09:00 IST via Celery Beat. Check upcoming deadlines and send reminders."""
    from app.engines.deadline_engine import compute_days_before_alert
    from app.models.client import Client
    from app.models.compliance_deadline import ComplianceDeadline
    from app.models.document import Document
    from app.models.whatsapp_reminder import WhatsAppReminder

    db = SessionLocal()
    try:
        today = date.today()
        window_end = today + timedelta(days=12)

        deadlines = (
            db.query(ComplianceDeadline)
            .filter(
                ComplianceDeadline.deadline <= window_end,
                ComplianceDeadline.deadline >= today,
                ComplianceDeadline.status == "pending",
            )
            .all()
        )

        for dl in deadlines:
            client = db.query(Client).filter(Client.id == dl.client_id).first()
            if not client or not client.whatsapp_consent_at:
                continue
            days_left = (dl.deadline - today).days
            if days_left > compute_days_before_alert(str(dl.client_id), dl.filing_type, db):
                continue

            if dl.doc_required:
                doc_received = (
                    db.query(Document)
                    .filter(
                        Document.client_id == dl.client_id,
                        Document.doc_type == dl.doc_required,
                        Document.status == "processed",
                    )
                    .first()
                )
                if doc_received:
                    continue

            reminder_count = (
                db.query(WhatsAppReminder)
                .filter(
                    WhatsAppReminder.client_id == dl.client_id,
                    WhatsAppReminder.deadline_id == dl.id,
                )
                .count()
            )
            if reminder_count >= 3:
                continue

            today_reminders = (
                db.query(WhatsAppReminder)
                .filter(
                    WhatsAppReminder.client_id == dl.client_id,
                    WhatsAppReminder.sent_at >= today,
                )
                .first()
            )
            if today_reminders:
                continue

            template = "filing_deadline_urgent" if days_left <= 1 else "data_request_reminder"
            params = [
                client.name,
                dl.filing_name,
                dl.deadline.strftime("%d %b"),
                dl.doc_required or "required documents",
            ]

            send_whatsapp_template.delay(
                client.whatsapp_number,
                template,
                params,
                str(dl.org_id),
                str(dl.client_id),
                str(dl.id),
            )
    finally:
        db.close()


@celery_app.task(queue="whatsapp")
def send_whatsapp_template(
    phone: str,
    template: str,
    params: list,
    org_id: str,
    client_id: str,
    deadline_id: str = None,
):
    """Send a WhatsApp template and log the reminder."""
    from app.config import settings
    from app.models.whatsapp_reminder import WhatsAppReminder
    from app.services.whatsapp_service import send_template

    db = SessionLocal()
    try:
        status = "sent"
        provider_response = {"mode": "development_fallback"}
        error_message = None
        try:
            if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
                provider_response = send_template(phone, template, params)
            else:
                logger.info("WhatsApp template dev fallback to %s: %s", phone, template)
        except Exception as exc:
            logger.error("WhatsApp send failed: %s", exc)
            status = "failed"
            error_message = str(exc)[:500]

        reminder = WhatsAppReminder(
            org_id=org_id,
            client_id=client_id,
            deadline_id=deadline_id,
            template=template,
            status=status,
            channel="whatsapp",
            provider_message_id=(provider_response.get("messages") or [{}])[0].get("id") if isinstance(provider_response, dict) else None,
            provider_response=provider_response if isinstance(provider_response, dict) else {"raw": str(provider_response)},
            error_message=error_message,
        )
        db.add(reminder)
        db.commit()
    finally:
        db.close()


def _handle_document(db, client, phone: str, message: dict[str, Any]) -> str:
    from app.config import settings
    from app.models.document import Document
    from app.services.s3_service import upload_bytes
    from app.services.whatsapp_service import download_media
    from app.tasks.ocr_tasks import run_ocr

    if not client.whatsapp_consent_at:
        _safe_send_text(phone, "Please opt in before sending documents. Reply START to enable WhatsApp support.")
        return "blocked_no_consent"

    doc_info = message.get("document") or {}
    media_id = doc_info.get("id")
    filename = doc_info.get("filename") or "whatsapp-document.pdf"
    mime_type = doc_info.get("mime_type")
    if not media_id:
        _safe_send_text(phone, "We could not read the document attachment. Please send it again.")
        return "missing_media_id"

    file_bytes = b""
    if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
        file_bytes = download_media(media_id)
    else:
        logger.info("WhatsApp media download dev fallback for media %s", media_id)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"
    key = f"tenants/{client.org_id}/clients/{client.id}/source_docs/{uuid.uuid4()}.{ext}"
    if file_bytes:
        upload_bytes(key, file_bytes)

    doc = Document(
        org_id=client.org_id,
        client_id=client.id,
        s3_key=key,
        source="whatsapp",
        doc_type=_detect_doc_type(filename),
        status="pending",
        original_filename=filename,
        mime_type=mime_type,
        file_size_bytes=str(len(file_bytes)) if file_bytes else None,
        received_at=datetime.now(timezone.utc),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    task = run_ocr.delay(str(doc.id))
    doc.celery_task_id = task.id
    db.commit()

    _safe_send_text(phone, f"Received {filename}. We are processing it now.")
    return "queued"


def process_incoming_wa(payload: dict):
    """Process incoming WhatsApp webhook payloads from FastAPI background tasks."""
    db = SessionLocal()
    summary = {
        "messages": 0,
        "unknown_numbers": 0,
        "consent_updates": 0,
        "documents_queued": 0,
        "ignored": 0,
    }
    try:
        for message in _iter_messages(payload):
            summary["messages"] += 1
            phone = message.get("from", "")
            msg_type = message.get("type", "")
            client = _find_client_by_phone(db, phone)

            if not client:
                summary["unknown_numbers"] += 1
                _safe_send_text(phone, "Your number is not registered. Please contact your CA.")
                continue

            if msg_type == "text":
                body = (message.get("text") or {}).get("body", "").strip()
                normalized_body = re.sub(r"\s+", " ", body.upper())
                if normalized_body in STOP_WORDS:
                    client.whatsapp_consent_at = None
                    db.commit()
                    summary["consent_updates"] += 1
                    _safe_send_text(phone, "You have been unsubscribed from WhatsApp reminders.")
                    continue
                if normalized_body in START_WORDS:
                    client.whatsapp_consent_at = datetime.now(timezone.utc)
                    db.commit()
                    summary["consent_updates"] += 1
                    _safe_send_text(phone, "WhatsApp support is enabled for your account.")
                    continue
                if not client.whatsapp_consent_at:
                    _safe_send_text(phone, "Please reply START to enable WhatsApp support for your account.")
                    continue
                _safe_send_text(phone, "Thanks. Our office has received your message.")
                continue

            if msg_type == "document":
                result = _handle_document(db, client, phone, message)
                if result == "queued":
                    summary["documents_queued"] += 1
                else:
                    summary["ignored"] += 1
                continue

            summary["ignored"] += 1

        return summary
    except Exception:
        logger.exception("WhatsApp webhook processing failed")
        raise
    finally:
        db.close()
