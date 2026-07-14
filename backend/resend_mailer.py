"""
Resend email delivery for the CA Copilot preview backend.

Design notes
------------
* Templates live in the Next.js frontend as React Email components.
* We call `POST {EMAIL_RENDER_URL}` (defaults to http://localhost:3000/api/emails/render)
  to render `{subject, html, text}` server-side.
* We then hand the payload to Resend via the official Python SDK.
* If `RESEND_API_KEY` starts with `re_placeholder` (or `RESEND_DRY_RUN=true`),
  every send is logged locally and no HTTP call is made — this keeps the
  preview environment usable without a real Resend account.
* Every send (real or dry-run) is appended to `EMAIL_LOG` which is what the
  UI reads at `GET /api/email/recent`.
* Webhook events (delivery, bounce, complaint) are verified with Svix and
  bounced addresses get added to `BOUNCED_ADDRESSES` so future sends
  short-circuit before hitting Resend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import httpx
import resend
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("ca_platform.email")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

RESEND_API_KEY: str = os.environ.get("RESEND_API_KEY", "").strip()
RESEND_FROM_EMAIL: str = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev").strip()
RESEND_FROM_NAME: str = os.environ.get("RESEND_FROM_NAME", "CA Copilot").strip()
RESEND_WEBHOOK_SECRET: str = os.environ.get("RESEND_WEBHOOK_SECRET", "").strip()
_DRY_RUN_ENV: str = os.environ.get("RESEND_DRY_RUN", "false").strip().lower()
EMAIL_RENDER_URL: str = os.environ.get(
    "EMAIL_RENDER_URL", "http://localhost:3000/api/emails/render"
).strip()


def is_placeholder() -> bool:
    return (not RESEND_API_KEY) or RESEND_API_KEY.startswith("re_placeholder")


def is_dry_run() -> bool:
    if _DRY_RUN_ENV in {"1", "true", "yes", "on"}:
        return True
    return is_placeholder()


def from_address() -> str:
    if RESEND_FROM_NAME:
        return f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>"
    return RESEND_FROM_EMAIL


# Configure Resend SDK (safe even with placeholder key — SDK is not called in dry-run).
if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY

# ---------------------------------------------------------------------------
# In-memory stores (preview stub)
# ---------------------------------------------------------------------------

EMAIL_LOG: List[Dict[str, Any]] = []
EMAIL_EVENTS: List[Dict[str, Any]] = []  # webhook events
BOUNCED_ADDRESSES: Set[str] = set()
_PROCESSED_SVIX_IDS: Set[str] = set()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Rendering — call the Next.js renderer for a React Email template
# ---------------------------------------------------------------------------


async def render_template(template: str, props: Dict[str, Any]) -> Dict[str, str]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(EMAIL_RENDER_URL, json={"template": template, "props": props})
        if r.status_code >= 400:
            detail = r.text
            try:
                detail = r.json().get("error", detail)
            except Exception:
                pass
            raise RuntimeError(f"Render failed ({r.status_code}): {detail}")
        return r.json()


def _fallback_html(template: str, props: Dict[str, Any]) -> Dict[str, str]:
    """If the Next.js renderer is unavailable, still produce a signal-shaped
    HTML payload so the send pipeline keeps working end-to-end (dry-run)."""
    subject = f"CA Copilot · {template.replace('_', ' ').title()}"
    body_rows = "".join(
        f"<tr><td style='padding:4px 12px;color:#94a3b8;font-family:monospace'>{k}</td>"
        f"<td style='padding:4px 0;font-family:monospace'>{v}</td></tr>"
        for k, v in props.items()
    )
    html = (
        "<div style='background:#050810;color:#e2e8f0;padding:24px;font-family:sans-serif'>"
        f"<div style='font:11px monospace;color:#22d3ee;letter-spacing:2px'>CA · COPILOT</div>"
        f"<h1 style='margin:8px 0 16px'>{subject}</h1>"
        f"<table>{body_rows}</table>"
        "</div>"
    )
    return {"subject": subject, "html": html, "text": subject}


# ---------------------------------------------------------------------------
# Core send API
# ---------------------------------------------------------------------------


async def send_email(
    *,
    template: str,
    to: str,
    props: Optional[Dict[str, Any]] = None,
    subject_override: Optional[str] = None,
    tags: Optional[Dict[str, str]] = None,
    org_id: str = "org-demo-001",
) -> Dict[str, Any]:
    """Render + send. Returns the log row (dry_run flag included).

    Never raises for a bad recipient — logs an entry with status="skipped_bounced".
    """
    props = props or {}
    tags = {"template": template, "org_id": org_id, **(tags or {})}
    to_normalised = (to or "").strip().lower()

    entry: Dict[str, Any] = {
        "id": f"em-{uuid.uuid4().hex[:12]}",
        "resend_message_id": None,
        "template": template,
        "recipient": to_normalised,
        "subject": subject_override or "",
        "status": "queued",
        "dry_run": is_dry_run(),
        "created_at": _now(),
        "updated_at": _now(),
        "tags": tags,
        "error": None,
    }

    # Guard: never send to a bounced address again
    if to_normalised in BOUNCED_ADDRESSES:
        entry["status"] = "skipped_bounced"
        entry["error"] = "Recipient previously bounced/complained — send suppressed."
        EMAIL_LOG.insert(0, entry)
        return entry

    # Render
    try:
        rendered = await render_template(template, props)
    except Exception as exc:
        log.warning("Template render failed for %s (%s) — falling back", template, exc)
        rendered = _fallback_html(template, props)

    entry["subject"] = subject_override or rendered.get("subject") or entry["subject"]
    html = rendered.get("html") or ""
    text = rendered.get("text") or ""

    # Dry-run: just log
    if is_dry_run():
        entry["status"] = "delivered"  # optimistic in preview — visible in UI
        entry["resend_message_id"] = f"re_dryrun_{uuid.uuid4().hex[:16]}"
        entry["dry_run"] = True
        EMAIL_LOG.insert(0, entry)
        log.info(
            "[email dry-run] template=%s to=%s subject=%s", template, to_normalised, entry["subject"]
        )
        return entry

    # Real send via Resend
    params: Dict[str, Any] = {
        "from": from_address(),
        "to": [to_normalised],
        "subject": entry["subject"],
        "html": html,
        "text": text,
        "tags": [{"name": k, "value": str(v)} for k, v in tags.items() if v is not None],
    }

    try:
        result = await asyncio.to_thread(resend.Emails.send, params)
        entry["resend_message_id"] = (
            result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
        )
        entry["status"] = "sent"
    except Exception as exc:
        entry["status"] = "failed"
        entry["error"] = str(exc)
        log.exception("Resend send failed for template=%s to=%s", template, to_normalised)

    entry["updated_at"] = _now()
    EMAIL_LOG.insert(0, entry)
    return entry


# ---------------------------------------------------------------------------
# Webhook (Svix)
# ---------------------------------------------------------------------------

BOUNCE_EVENTS = {"email.bounced", "email.complained"}
STATUS_MAP = {
    "email.sent": "sent",
    "email.delivered": "delivered",
    "email.delivery_delayed": "delayed",
    "email.bounced": "bounced",
    "email.complained": "complained",
    "email.opened": "opened",
    "email.clicked": "clicked",
}


def verify_and_parse_webhook(raw_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
    """Verify Svix signature (if RESEND_WEBHOOK_SECRET configured) then return parsed payload."""
    from svix.webhooks import Webhook, WebhookVerificationError

    hdr = {k.lower(): v for k, v in headers.items()}
    svix_id = hdr.get("svix-id") or ""
    svix_ts = hdr.get("svix-timestamp") or ""
    svix_sig = hdr.get("svix-signature") or ""

    if RESEND_WEBHOOK_SECRET and not RESEND_WEBHOOK_SECRET.startswith("whsec_placeholder"):
        if not (svix_id and svix_ts and svix_sig):
            raise ValueError("Missing svix headers")
        try:
            wh = Webhook(RESEND_WEBHOOK_SECRET)
            return wh.verify(raw_body, {"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": svix_sig})
        except WebhookVerificationError as exc:
            raise ValueError(f"Invalid signature: {exc}")
    # Placeholder / dev mode — parse without verifying
    import json

    return json.loads(raw_body.decode("utf-8"))


def record_webhook_event(payload: Dict[str, Any], svix_id: Optional[str] = None) -> Dict[str, Any]:
    """Persist the event, update send-log status, blacklist bounces."""
    if svix_id:
        if svix_id in _PROCESSED_SVIX_IDS:
            return {"ok": True, "deduped": True}
        _PROCESSED_SVIX_IDS.add(svix_id)

    event_type = payload.get("type") or payload.get("event") or "unknown"
    data = payload.get("data") or {}
    message_id = data.get("email_id") or data.get("id")

    recipient: Optional[str] = None
    to = data.get("to")
    if isinstance(to, list) and to:
        recipient = str(to[0]).lower()
    elif isinstance(to, str):
        recipient = to.lower()

    row = {
        "id": f"evt-{uuid.uuid4().hex[:12]}",
        "resend_event_id": svix_id,
        "resend_message_id": message_id,
        "event_type": event_type,
        "recipient": recipient,
        "received_at": _now(),
        "raw": data,
    }
    EMAIL_EVENTS.insert(0, row)

    # Update log status
    new_status = STATUS_MAP.get(event_type)
    if new_status and message_id:
        for entry in EMAIL_LOG:
            if entry.get("resend_message_id") == message_id:
                entry["status"] = new_status
                entry["updated_at"] = _now()
                break

    # Blacklist bounces / complaints
    if event_type in BOUNCE_EVENTS and recipient:
        BOUNCED_ADDRESSES.add(recipient)

    return {"ok": True, "event": event_type, "recipient": recipient}


# ---------------------------------------------------------------------------
# Seed a few historical rows so the UI isn't empty on first load
# ---------------------------------------------------------------------------


def seed_demo_log(clients: List[Dict[str, Any]]) -> None:
    if EMAIL_LOG:
        return
    import random

    templates = list(STATUS_MAP.keys())[:1]  # unused, kept for future
    templates = [
        "password_reset",
        "email_verification",
        "user_invitation",
        "invoice_sent",
        "payment_received",
        "invoice_overdue",
        "subscription_activated",
        "subscription_cancelled",
        "document_request",
        "portal_invite",
        "report_ready",
    ]
    for i in range(14):
        seed = random.Random(i + 41)
        tpl = seed.choice(templates)
        client = seed.choice(clients) if clients else {"name": "Aurora Textiles", "email": "contact@aurora.in"}
        EMAIL_LOG.append(
            {
                "id": f"em-seed-{i:04d}",
                "resend_message_id": f"re_{seed.randbytes(8).hex()}",
                "template": tpl,
                "recipient": client.get("email", f"user{i}@example.com"),
                "subject": f"{tpl.replace('_', ' ').title()} · {client.get('name', 'Client')}",
                "status": seed.choice(["delivered", "delivered", "delivered", "sent", "bounced", "delayed"]),
                "dry_run": True,
                "created_at": (datetime.now(timezone.utc)).isoformat(),
                "updated_at": _now(),
                "tags": {"template": tpl, "org_id": "org-demo-001"},
                "error": None,
            }
        )


__all__ = [
    "send_email",
    "render_template",
    "verify_and_parse_webhook",
    "record_webhook_event",
    "seed_demo_log",
    "is_dry_run",
    "is_placeholder",
    "from_address",
    "EMAIL_LOG",
    "EMAIL_EVENTS",
    "BOUNCED_ADDRESSES",
]
