"""FastAPI router for Resend email events + admin utilities.

Mounted at `/email` from main.py → browser URL is `/api/email/*`.

Endpoints:
  * `POST /api/email/webhook` — Resend/Svix webhook receiver
  * `GET  /api/email/config`  — public bootstrap (dry-run status, from address)
  * `GET  /api/email/recent`  — last 50 outbound sends for the tenant
  * `POST /api/email/test-send` — dev helper (dry-run) to fire a template with sample data
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.email_models import EmailEvent, EmailSendLog
from app.models.user import User
from app.services import resend_service as rs
from app.utils.deps import require_user

router = APIRouter()
log = logging.getLogger("ca_platform.email.router")


BOUNCE_EVENTS = {"email.bounced", "email.complained", "email.delivery_delayed"}


class TestSendIn(BaseModel):
    to: EmailStr
    template: str = "email_verification"
    cta_url: str = "https://example.com/dashboard"


@router.get("/config")
def config():
    return {
        "provider": "resend",
        "dry_run": rs._dry_run(),
        "from": rs._from_address(),
        "webhook_configured": bool(getattr(settings, "RESEND_WEBHOOK_SECRET", "")),
    }


@router.post("/webhook", include_in_schema=False)
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    try:
        payload = rs.verify_webhook(raw, dict(request.headers))
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Webhook parse error: {exc}")

    event_type = payload.get("type") or payload.get("event") or "unknown"
    data = payload.get("data") or {}
    resend_message_id = data.get("email_id") or data.get("id")
    recipient = None
    to = data.get("to")
    if isinstance(to, list) and to:
        recipient = to[0]
    elif isinstance(to, str):
        recipient = to
    tags = data.get("tags") or []
    tags_map: dict[str, str] = {}
    if isinstance(tags, list):
        for t in tags:
            if isinstance(t, dict) and "name" in t and "value" in t:
                tags_map[t["name"]] = t["value"]

    svix_id = request.headers.get("svix-id") or request.headers.get("Svix-Id")
    # Idempotency dedupe
    if svix_id:
        existing = db.query(EmailEvent).filter(EmailEvent.resend_event_id == svix_id).first()
        if existing:
            return {"ok": True, "deduped": True}

    row = EmailEvent(
        org_id=tags_map.get("org_id") if tags_map.get("org_id") not in ("unknown", "", None) else None,
        resend_event_id=svix_id,
        resend_message_id=resend_message_id,
        event_type=event_type,
        recipient=recipient,
        template=tags_map.get("template"),
        tags=tags_map,
        payload=payload,
    )
    db.add(row)

    # Reduce into EmailSendLog + users table
    try:
        if resend_message_id:
            log_row = (
                db.query(EmailSendLog)
                .filter(EmailSendLog.resend_message_id == resend_message_id)
                .first()
            )
            if log_row:
                mapping = {
                    "email.sent": "sent",
                    "email.delivered": "delivered",
                    "email.bounced": "bounced",
                    "email.complained": "complained",
                    "email.delivery_delayed": "delayed",
                    "email.opened": log_row.status,       # don't downgrade
                    "email.clicked": log_row.status,
                }
                new_status = mapping.get(event_type)
                if new_status:
                    log_row.status = new_status
                log_row.updated_at = datetime.now(timezone.utc)

        # Mark bouncing users so we stop future sends
        if event_type in BOUNCE_EVENTS and recipient:
            user = db.query(User).filter(User.email == recipient.lower()).first()
            if user and hasattr(user, "email_bounced_at"):
                user.email_bounced_at = datetime.now(timezone.utc)

        row.handled_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        row.handle_error = str(exc)[:500]
        log.exception("email.webhook.reduce failed event=%s: %s", event_type, exc)
    finally:
        db.commit()

    return {"ok": True, "event": event_type}


@router.get("/recent")
def recent(db: Session = Depends(get_db), user=Depends(require_user)):
    rows = (
        db.query(EmailSendLog)
        .filter(EmailSendLog.org_id == user.org_id)
        .order_by(EmailSendLog.created_at.desc())
        .limit(50)
        .all()
    )
    return [{
        "id": r.id,
        "resend_message_id": r.resend_message_id,
        "template": r.template,
        "recipient": r.recipient,
        "subject": r.subject,
        "status": r.status,
        "dry_run": r.dry_run == "true",
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
        "tags": r.tags or {},
    } for r in rows]


@router.post("/test-send")
async def test_send(body: TestSendIn, user=Depends(require_user)):
    """Dev helper — fires any template through the pipeline.
    In dry-run mode this just logs; when real key is set it sends."""
    try:
        result = await rs.send_email(
            to=body.to,
            template=body.template,
            context={
                "name": user.email.split("@")[0],
                "cta_url": body.cta_url,
                "headline": "Test signal from CA Copilot",
                "meta": [("Template", body.template), ("Environment", getattr(settings, "ENV", "dev"))],
                "invoice_no": "INV-2026-TEST-001",
                "amount_str": "12,999",
                "client_name": "Aurora Textiles",
                "plan_name": "Pro",
                "org_name": "Nova & Partners",
                "inviter_name": "Priya Nair",
                "role": "article",
                "kind": "Bank statement",
                "due_by": "2026-01-31",
                "report_title": "Draft GST reconciliation · Dec 2025",
                "days_overdue": 5,
            },
            org_id=str(user.org_id),
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "ok": True,
        "id": result.id,
        "dry_run": result.dry_run,
        "template": result.template,
        "subject": result.subject,
    }
