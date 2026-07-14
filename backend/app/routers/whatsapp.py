from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional
import re

from app.database import get_db
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped
from app.utils.events import publish_event

router = APIRouter()
PHONE_RE = re.compile(r"^\+?[1-9][0-9]{9,14}$")


class ManualReminderRequest(BaseModel):
    client_id: str
    message: str = Field(min_length=1, max_length=1000)
    deadline_id: Optional[str] = None


def _normalize_phone(phone: str) -> str:
    normalized = re.sub(r"[\s\-()]", "", phone.strip())
    if not PHONE_RE.match(normalized):
        raise HTTPException(422, "Invalid WhatsApp phone number")
    return normalized


@router.get("/consent/{token}", response_class=HTMLResponse)
def whatsapp_consent(token: str, db: Session = Depends(get_db)):
    """No auth required. Client clicks this link to opt in."""
    from app.models.client import Client
    from app.services.whatsapp_service import verify_consent_token

    client_id = verify_consent_token(token)
    client = db.query(Client).filter(Client.id == client_id).first()
    if client:
        client.whatsapp_consent_at = datetime.now(timezone.utc)
        db.commit()

    return HTMLResponse("""
    <html>
    <body style="font-family:sans-serif;max-width:400px;margin:60px auto;text-align:center">
      <h2>✅ Done!</h2>
      <p>Your CA's office will now send document reminders to this WhatsApp number.</p>
      <p style="color:#888;font-size:13px">Reply <strong>STOP</strong> at any time to unsubscribe.</p>
    </body>
    </html>
    """)


@router.get("/webhook")
def verify_webhook(request: Request):
    """Meta webhook verification handshake."""
    mode      = request.query_params.get("hub.mode")
    token     = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    from app.config import settings
    if mode == "subscribe" and token == getattr(settings, "WHATSAPP_VERIFY_TOKEN", "verify") and challenge is not None:
        return PlainTextResponse(challenge)
    raise HTTPException(403, "Forbidden")


@router.post("/webhook")
async def wa_webhook(request: Request, background_tasks: BackgroundTasks):
    """Return 200 immediately — process message in background."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    from app.tasks.whatsapp_tasks import process_incoming_wa
    background_tasks.add_task(process_incoming_wa, payload)
    return {"status": "ok"}


@router.post("/send-manual")
def send_manual(payload: ManualReminderRequest, request: Request,
                db: Session = Depends(get_db),
                _=Depends(require_role(["partner", "manager"]))):
    from app.models.client import Client
    from app.models.compliance_deadline import ComplianceDeadline
    from app.models.whatsapp_reminder import WhatsAppReminder
    from app.config import settings
    from app.services.whatsapp_service import send_text

    message = payload.message.strip()
    if not message or len(message) > 1000:
        raise HTTPException(422, "Message must be between 1 and 1000 characters")
    client = scoped(db, Client, request.state.org_id).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    if not client.whatsapp_number:
        raise HTTPException(409, "Client WhatsApp number is required")
    phone = _normalize_phone(client.whatsapp_number)
    if payload.deadline_id:
        deadline = scoped(db, ComplianceDeadline, request.state.org_id).filter(
            ComplianceDeadline.id == payload.deadline_id,
            ComplianceDeadline.client_id == client.id,
        ).first()
        if not deadline:
            raise HTTPException(404, "Deadline not found for client")
    if not client:
        raise HTTPException(400, "Client is not opted in for WhatsApp messages")
    if not client.whatsapp_consent_at:
        raise HTTPException(400, "Client is not opted in for WhatsApp messages")
    status = "sent"
    provider_response = {"mode": "development_fallback"}
    provider_message_id = None
    try:
        if settings.WHATSAPP_TOKEN and settings.WHATSAPP_PHONE_ID:
            provider_response = send_text(phone, message)
            provider_message_id = (provider_response.get("messages") or [{}])[0].get("id")
    except Exception as exc:
        status = "failed"
        db.add(WhatsAppReminder(
            org_id=request.state.org_id,
            client_id=client.id,
            deadline_id=payload.deadline_id,
            template="manual",
            status=status,
            channel="whatsapp",
            provider_response=provider_response,
            provider_message_id=provider_message_id,
            error_message=str(exc)[:500],
        ))
        publish_event(
            db,
            org_id=request.state.org_id,
            actor_id=request.state.user_id,
            event_type="integration.whatsapp.send_failed",
            aggregate_type="client",
            aggregate_id=str(client.id),
            source_module="whatsapp",
            payload={"template": "manual", "error": str(exc)[:500], "provider_mode": provider_response.get("mode")},
            status="failed",
        )
        db.commit()
        raise HTTPException(503, f"WhatsApp provider unavailable: {exc}") from exc
    reminder = WhatsAppReminder(
        org_id=request.state.org_id,
        client_id=client.id,
        deadline_id=payload.deadline_id,
        template="manual",
        status=status,
        channel="whatsapp",
        provider_response=provider_response,
        provider_message_id=provider_message_id,
    )
    db.add(reminder)
    publish_event(
        db,
        org_id=request.state.org_id,
        actor_id=request.state.user_id,
        event_type="integration.whatsapp.message_sent",
        aggregate_type="client",
        aggregate_id=str(client.id),
        source_module="whatsapp",
        payload={"template": "manual", "provider_message_id": provider_message_id, "provider_mode": provider_response.get("mode")},
    )
    db.commit()
    return {
        "sent": True,
        "status": status,
        "client_id": str(client.id),
        "whatsapp_number": phone,
        "provider_response": provider_response,
    }


@router.post("/consent-link/{client_id}")
def create_consent_link(client_id: str, request: Request, db: Session = Depends(get_db),
                        _=Depends(require_role(["partner", "manager"]))):
    from app.models.client import Client
    from app.services.whatsapp_service import generate_consent_token

    client = scoped(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    if not client.whatsapp_number:
        raise HTTPException(409, "Client WhatsApp number is required before consent link generation")
    token, expires_at = generate_consent_token(str(client.id))
    return {
        "client_id": str(client.id),
        "whatsapp_number": client.whatsapp_number,
        "already_consented": bool(client.whatsapp_consent_at),
        "expires_at": datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat(),
        "consent_url": f"{str(request.base_url).rstrip('/')}/whatsapp/consent/{token}",
    }


@router.get("/status")
def whatsapp_status(request: Request, db: Session = Depends(get_db),
                    skip: int = 0, limit: int = 2000, _=Depends(get_current_user)):
    from app.models.client import Client
    from app.models.compliance_deadline import ComplianceDeadline
    from app.models.whatsapp_reminder import WhatsAppReminder

    if skip < 0:
        raise HTTPException(422, "skip must be >= 0")
    if limit < 1 or limit > 5000:
        raise HTTPException(422, "limit must be between 1 and 5000")
    clients = (scoped(db, Client, request.state.org_id)
               .filter(Client.whatsapp_number.isnot(None))
               .order_by(Client.name.asc())
               .offset(skip).limit(limit).all())
    client_ids = [c.id for c in clients]

    last_sent = (
        scoped(db, WhatsAppReminder, request.state.org_id)
        .with_entities(WhatsAppReminder.client_id, func.max(WhatsAppReminder.sent_at).label("sent_at"))
        .filter(WhatsAppReminder.client_id.in_(client_ids))
        .group_by(WhatsAppReminder.client_id)
        .subquery()
    )
    reminder_rows = []
    if client_ids:
        reminder_rows = (
            scoped(db, WhatsAppReminder, request.state.org_id)
            .join(last_sent, (WhatsAppReminder.client_id == last_sent.c.client_id) & (WhatsAppReminder.sent_at == last_sent.c.sent_at))
            .all()
        )
    last_by_client = {row.client_id: row for row in reminder_rows}
    reminder_stats = {client_id: {"sent": 0, "failed": 0, "total": 0, "last_failure": None} for client_id in client_ids}
    if client_ids:
        stat_rows = (
            scoped(db, WhatsAppReminder, request.state.org_id)
            .with_entities(
                WhatsAppReminder.client_id,
                WhatsAppReminder.status,
                func.count(WhatsAppReminder.id).label("count"),
            )
            .filter(WhatsAppReminder.client_id.in_(client_ids))
            .group_by(WhatsAppReminder.client_id, WhatsAppReminder.status)
            .all()
        )
        for client_id, status_value, count in stat_rows:
            bucket = reminder_stats.setdefault(client_id, {"sent": 0, "failed": 0, "total": 0, "last_failure": None})
            bucket[status_value] = int(count)
            bucket["total"] += int(count)
        failure_rows = (
            scoped(db, WhatsAppReminder, request.state.org_id)
            .filter(WhatsAppReminder.client_id.in_(client_ids), WhatsAppReminder.status == "failed")
            .order_by(WhatsAppReminder.client_id.asc(), WhatsAppReminder.sent_at.desc())
            .all()
        )
        seen_failures = set()
        for failure in failure_rows:
            if failure.client_id in seen_failures:
                continue
            seen_failures.add(failure.client_id)
            reminder_stats.setdefault(failure.client_id, {"sent": 0, "failed": 0, "total": 0, "last_failure": None})["last_failure"] = failure

    deadlines_by_client = {client_id: [] for client_id in client_ids}
    if client_ids:
        deadline_rows = (
            scoped(db, ComplianceDeadline, request.state.org_id)
            .filter(ComplianceDeadline.client_id.in_(client_ids), ComplianceDeadline.status != "filed")
            .order_by(ComplianceDeadline.client_id.asc(), ComplianceDeadline.deadline.asc())
            .all()
        )
        for deadline in deadline_rows:
            bucket = deadlines_by_client.setdefault(deadline.client_id, [])
            if len(bucket) < 8:
                bucket.append(deadline)

    result = []
    for c in clients:
        last_reminder = last_by_client.get(c.id)
        stats = reminder_stats.get(c.id, {"sent": 0, "failed": 0, "total": 0, "last_failure": None})
        last_failure = stats.get("last_failure")
        deadlines = deadlines_by_client.get(c.id, [])
        result.append({
            "client_id": str(c.id), "name": c.name,
            "whatsapp_number": c.whatsapp_number,
            "consent": bool(c.whatsapp_consent_at),
            "consent_at": c.whatsapp_consent_at.isoformat() if c.whatsapp_consent_at else None,
            "consent_status": "opted_in" if c.whatsapp_consent_at else "missing",
            "reminder_total": stats.get("total", 0),
            "reminder_sent": stats.get("sent", 0),
            "reminder_failed": stats.get("failed", 0),
            "last_reminder_id": str(last_reminder.id) if last_reminder else None,
            "last_reminder_status": last_reminder.status if last_reminder else None,
            "last_reminder_at": last_reminder.sent_at.isoformat() if last_reminder else None,
            "last_template": last_reminder.template if last_reminder else None,
            "last_provider_mode": (last_reminder.provider_response or {}).get("mode") if last_reminder else None,
            "last_provider_message_id": last_reminder.provider_message_id if last_reminder else None,
            "last_error_message": last_failure.error_message if last_failure else None,
            "last_failed_at": last_failure.sent_at.isoformat() if last_failure else None,
            "pending_filings": [
                {
                    "filing_type": d.filing_type, "filing_name": d.filing_name,
                    "period": d.period, "deadline": str(d.deadline), "status": d.status,
                }
                for d in deadlines
            ],
        })
    return result
