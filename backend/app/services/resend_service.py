"""
Resend transactional email service.

Handles every transactional email in CA Copilot:
  - Auth: password reset, email verification, invitations
  - Billing: invoice sent, payment received, invoice overdue, subscription events
  - Portal: document requests, contact invites, report ready

Uses the official `resend` Python SDK (resend>=2.0.0). All send calls run in a
thread pool via `asyncio.to_thread` to keep FastAPI non-blocking.

Modes:
  - `RESEND_DRY_RUN=true` (or when API key is placeholder / missing) → log the
    render payload; DO NOT hit the Resend API. Every code path still runs so
    dev environments don't fail.
  - Live mode → hits the Resend Emails API.

Templates are rendered inline (no Jinja2 dep) with a single HUD-branded
master shell so all mails look premium out-of-the-box.
"""
from __future__ import annotations

import asyncio
import html as htmllib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from app.config import settings

logger = logging.getLogger("ca_platform.resend")

# The SDK is imported at module level but the key is set lazily so tests /
# preview environments without a real key don't blow up.
try:
    import resend as _resend_sdk  # type: ignore
except Exception:  # pragma: no cover
    _resend_sdk = None


def _dry_run() -> bool:
    key = (settings.RESEND_API_KEY or "").strip()
    if getattr(settings, "RESEND_DRY_RUN", False):
        return True
    if not key or key.startswith("re_placeholder") or key.lower() == "placeholder":
        return True
    return False


def _configure_sdk() -> None:
    if _resend_sdk is not None:
        _resend_sdk.api_key = settings.RESEND_API_KEY


def _from_address() -> str:
    name = getattr(settings, "RESEND_FROM_NAME", "CA Copilot") or "CA Copilot"
    email = getattr(settings, "RESEND_FROM_EMAIL", "onboarding@resend.dev") or "onboarding@resend.dev"
    return f"{name} <{email}>"


# ---------------------------------------------------------------------------
# HUD-branded master shell — all templates render into this shell.
# Every template body must use inline CSS (email client compat).
# ---------------------------------------------------------------------------

_MASTER_SHELL = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <meta name="color-scheme" content="dark" />
  <meta name="supported-color-schemes" content="dark" />
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#05070d;font-family:'Manrope',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;color:#cbd5f5;">
  <div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#05070d;">{preheader}</div>
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#05070d;padding:32px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:linear-gradient(180deg,#0c1122,#080b16);border:1px solid rgba(148,163,214,0.16);border-radius:20px;overflow:hidden;box-shadow:0 24px 60px -20px rgba(0,0,0,0.55);">
          <!-- top signal bar -->
          <tr><td style="height:2px;background:linear-gradient(90deg,transparent,rgba(34,211,238,0.7),rgba(167,139,250,0.5),transparent);"></td></tr>
          <!-- brand row -->
          <tr>
            <td style="padding:24px 28px 8px 28px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
                <tr>
                  <td>
                    <span style="font-family:'JetBrains Mono',ui-monospace,Consolas,monospace;font-size:10px;font-weight:600;letter-spacing:0.28em;color:#22d3ee;text-transform:uppercase;">
                      {eyebrow}
                    </span>
                    <div style="height:6px;line-height:6px;font-size:0;">&nbsp;</div>
                    <span style="font-family:'Manrope',Arial,sans-serif;font-size:22px;font-weight:600;color:#f4f7ff;letter-spacing:-0.01em;">
                      {headline}
                    </span>
                  </td>
                  <td align="right" style="width:56px;">
                    <div style="width:44px;height:44px;border-radius:14px;background:radial-gradient(circle at 50% 50%,#ecfeff,#22d3ee 40%,#0e7490 74%);border:1px solid rgba(103,232,249,0.55);box-shadow:0 0 22px rgba(34,211,238,0.4);"></div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- body -->
          <tr>
            <td style="padding:12px 28px 24px 28px;font-size:14.5px;line-height:1.6;color:#cbd5f5;">
              {body}
            </td>
          </tr>
          <!-- CTA if provided -->
          {cta_block}
          <!-- meta strip -->
          {meta_block}
          <!-- footer -->
          <tr><td style="border-top:1px solid rgba(148,163,214,0.16);padding:16px 28px;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="font-family:'JetBrains Mono',ui-monospace,Consolas,monospace;font-size:10px;letter-spacing:0.24em;color:#5a668a;text-transform:uppercase;">
                  CA · Copilot · Practice OS × AI
                </td>
                <td align="right" style="font-family:'JetBrains Mono',ui-monospace,Consolas,monospace;font-size:10px;letter-spacing:0.2em;color:#5a668a;text-transform:uppercase;">
                  {sent_at}
                </td>
              </tr>
            </table>
          </td></tr>
          <tr><td style="height:2px;background:linear-gradient(90deg,transparent,rgba(167,139,250,0.5),transparent);"></td></tr>
        </table>
        <!-- legal -->
        <div style="padding:16px 8px;font-size:11px;color:#3a4568;font-family:'Manrope',Arial,sans-serif;max-width:600px;line-height:1.55;">
          You&#8217;re receiving this from CA Copilot because your firm uses our platform. If this isn&#8217;t you,
          you can safely ignore this mail. Replies are not monitored — reach us through the app instead.
        </div>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _cta(url: str, label: str, tone: str = "cyan") -> str:
    bg = {
        "cyan":   "linear-gradient(180deg,#22d3ee,#0e7490)",
        "violet": "linear-gradient(180deg,#a78bfa,#6d28d9)",
        "rose":   "linear-gradient(180deg,#fb7185,#be123c)",
    }.get(tone, "linear-gradient(180deg,#22d3ee,#0e7490)")
    return (
        '<tr><td style="padding:4px 28px 24px 28px;">'
        '<table role="presentation" cellpadding="0" cellspacing="0"><tr><td>'
        f'<a href="{htmllib.escape(url, quote=True)}" '
        f'style="display:inline-block;background:{bg};color:#041018;font-weight:600;'
        'font-family:Manrope,Arial,sans-serif;font-size:14px;padding:12px 22px;'
        'border-radius:12px;text-decoration:none;letter-spacing:0.01em;'
        'box-shadow:0 12px 30px -8px rgba(34,211,238,0.55);">'
        f'{htmllib.escape(label)} &nbsp;&#8594;</a>'
        '</td></tr></table></td></tr>'
    )


def _meta(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return ""
    inner = "".join(
        '<tr>'
        f'<td style="padding:6px 0;font-family:\'JetBrains Mono\',ui-monospace,Consolas,monospace;'
        'font-size:10px;letter-spacing:0.22em;color:#5a668a;text-transform:uppercase;width:35%;">'
        f'{htmllib.escape(k)}</td>'
        f'<td style="padding:6px 0;color:#f4f7ff;font-family:Manrope,Arial,sans-serif;font-size:13px;">'
        f'{htmllib.escape(v)}</td></tr>'
        for k, v in rows
    )
    return (
        '<tr><td style="padding:0 28px 20px 28px;">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:rgba(9,14,32,0.55);border:1px solid rgba(148,163,214,0.16);border-radius:12px;padding:8px 14px;">'
        f'{inner}</table></td></tr>'
    )


def _to_plain_text(html: str) -> str:
    """Best-effort HTML → plain-text fallback (email clients that block HTML)."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return htmllib.unescape(text).strip()


# ---------------------------------------------------------------------------
# Template registry — HUD-branded copy for every mail we send.
# ---------------------------------------------------------------------------

@dataclass
class Rendered:
    subject: str
    html: str
    text: str
    template: str


def _render(template: str, ctx: dict[str, Any]) -> Rendered:
    t = TEMPLATES.get(template)
    if not t:
        raise KeyError(f"Unknown email template: {template}")
    subject = t["subject"].format(**ctx)
    body_html = t["body"](ctx)
    cta_block = _cta(ctx["cta_url"], ctx.get("cta_label") or t.get("cta_label", "Open CA Copilot"),
                     t.get("cta_tone", "cyan")) if ctx.get("cta_url") else ""
    meta_block = _meta(list(ctx.get("meta", [])))
    html = _MASTER_SHELL.format(
        subject=htmllib.escape(subject),
        preheader=htmllib.escape(ctx.get("preheader") or subject),
        eyebrow=htmllib.escape(t.get("eyebrow", "CA COPILOT · SIGNAL")),
        headline=htmllib.escape(ctx.get("headline") or t.get("headline", subject)),
        body=body_html,
        cta_block=cta_block,
        meta_block=meta_block,
        sent_at=datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M UTC"),
    )
    return Rendered(subject=subject, html=html, text=_to_plain_text(html), template=template)


def _p(text: str) -> str:
    return f'<p style="margin:0 0 12px 0;">{text}</p>'


TEMPLATES: dict[str, dict[str, Any]] = {
    # ---- Auth ---------------------------------------------------------------
    "password_reset": {
        "subject": "Reset your CA Copilot access key",
        "eyebrow": "SECURITY · PASSWORD RESET",
        "cta_label": "Reset access key",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"Hi{ ' ' + htmllib.escape(c.get('name') or '') if c.get('name') else '' },")
            + _p("Someone (hopefully you) requested a password reset for your CA Copilot account. "
                 "Tap the button below within the next hour to set a new key.")
            + _p("<span style='color:#8b96b8;font-size:13px;'>If you didn&#39;t request this, ignore this email — "
                 "your current key still works.</span>")
        ),
    },
    "email_verification": {
        "subject": "Verify your CA Copilot email",
        "eyebrow": "IDENTITY · VERIFY EMAIL",
        "cta_label": "Verify email",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"Welcome to CA Copilot{ ', ' + htmllib.escape(c.get('name') or '') if c.get('name') else '' }.")
            + _p("One quick step: verify this email so notifications and password resets reach you.")
        ),
    },
    "user_invitation": {
        "subject": "You've been invited to {org_name} on CA Copilot",
        "eyebrow": "TEAM · INVITATION",
        "cta_label": "Accept invitation",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"<strong style='color:#f4f7ff;'>{htmllib.escape(c.get('inviter_name') or 'A partner')}</strong> "
               f"has invited you to join <strong style='color:#f4f7ff;'>{htmllib.escape(c.get('org_name', 'their workspace'))}</strong> "
               "on CA Copilot as a <span style='color:#22d3ee;font-family:JetBrains Mono,monospace;font-size:12px;letter-spacing:0.2em;text-transform:uppercase;'>"
               f"{htmllib.escape(c.get('role', 'article'))}</span>.")
            + _p("Accept your invite to spin up your terminal — the link expires in 72 hours.")
        ),
    },
    # ---- Billing ------------------------------------------------------------
    "invoice_sent": {
        "subject": "Invoice {invoice_no} · ₹{amount_str}",
        "eyebrow": "BILLING · INVOICE ISSUED",
        "cta_label": "Pay now via Razorpay",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"Hello {htmllib.escape(c.get('client_name') or 'there')},")
            + _p(f"Your CA has issued a new invoice — <strong style='color:#f4f7ff;'>{htmllib.escape(c.get('invoice_no',''))}</strong>.")
            + _p("Pay in one tap via UPI, cards, netbanking, wallets, or EMI. The link is secure and expires with the invoice.")
        ),
    },
    "payment_received": {
        "subject": "Payment received · ₹{amount_str}",
        "eyebrow": "BILLING · PAYMENT CONFIRMED",
        "cta_label": "Open receipt",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"Thanks {htmllib.escape(c.get('client_name') or '')} — we&#39;ve received your payment of "
               f"<strong style='color:#6ee7b7;'>₹{htmllib.escape(c.get('amount_str', ''))}</strong> "
               f"for invoice <strong style='color:#f4f7ff;'>{htmllib.escape(c.get('invoice_no', ''))}</strong>.")
            + _p("A receipt PDF is attached to your CA Copilot portal.")
        ),
    },
    "invoice_overdue": {
        "subject": "Reminder · Invoice {invoice_no} overdue",
        "eyebrow": "BILLING · OVERDUE REMINDER",
        "cta_label": "Settle now",
        "cta_tone": "rose",
        "body": lambda c: (
            _p(f"Hi {htmllib.escape(c.get('client_name') or 'there')},")
            + _p(f"Invoice <strong style='color:#f4f7ff;'>{htmllib.escape(c.get('invoice_no',''))}</strong> "
                 f"of <strong style='color:#fda4af;'>₹{htmllib.escape(c.get('amount_str',''))}</strong> "
                 f"is <strong style='color:#fda4af;'>{htmllib.escape(str(c.get('days_overdue', 0)))} day(s) overdue</strong>. "
                 "Settle it now to avoid late fees.")
        ),
    },
    "subscription_activated": {
        "subject": "Your CA Copilot {plan_name} subscription is live",
        "eyebrow": "SUBSCRIPTION · ACTIVE",
        "cta_label": "Open command center",
        "cta_tone": "violet",
        "body": lambda c: (
            _p(f"Welcome to CA Copilot <strong style='color:#c4b5fd;'>{htmllib.escape(c.get('plan_name',''))}</strong>. "
               "Autopay is now armed and your next charge date is shown below.")
            + _p("Everything on your plan is enabled instantly — no restart required.")
        ),
    },
    "subscription_cancelled": {
        "subject": "Your CA Copilot subscription is scheduled to end",
        "eyebrow": "SUBSCRIPTION · CANCELLED",
        "cta_label": "Reactivate",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p("Your subscription will remain active until the end of the current billing cycle, then stop.")
            + _p("Change your mind? Reactivate any time from Billing → Payments · Razorpay.")
        ),
    },
    # ---- Portal -------------------------------------------------------------
    "document_request": {
        "subject": "New document request · {client_name}",
        "eyebrow": "PORTAL · DOCUMENT REQUEST",
        "cta_label": "Upload documents",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"Your CA has requested a document to move <strong style='color:#f4f7ff;'>{htmllib.escape(c.get('kind', 'a filing'))}</strong> forward.")
            + _p(f"<span style='color:#8b96b8;font-size:13px;'>Deadline: <strong style='color:#fcd34d;'>{htmllib.escape(c.get('due_by', 'ASAP'))}</strong></span>")
        ),
    },
    "portal_invite": {
        "subject": "You&rsquo;ve been invited to your CA&rsquo;s secure portal",
        "eyebrow": "PORTAL · INVITATION",
        "cta_label": "Enter portal",
        "cta_tone": "cyan",
        "body": lambda c: (
            _p(f"{htmllib.escape(c.get('inviter_name') or 'Your CA')} has invited you to their secure client portal on CA Copilot.")
            + _p("Upload files, approve deliverables, and chat securely — everything auditable, GDPR-friendly, and end-to-end encrypted in transit.")
        ),
    },
    "report_ready": {
        "subject": "Your CA report is ready · {report_title}",
        "eyebrow": "DELIVERY · REPORT READY",
        "cta_label": "View report",
        "cta_tone": "violet",
        "body": lambda c: (
            _p(f"<strong style='color:#f4f7ff;'>{htmllib.escape(c.get('report_title',''))}</strong> is ready for your review.")
            + _p("Open the report on your secure portal to view, download, or share.")
        ),
    },
}


# ---------------------------------------------------------------------------
# Public API — send
# ---------------------------------------------------------------------------

@dataclass
class SendResult:
    id: str
    dry_run: bool
    template: str
    subject: str


async def send_email(
    *,
    to: str | list[str],
    template: str,
    context: dict[str, Any] | None = None,
    org_id: str | None = None,
    idempotency_key: str | None = None,
    reply_to: str | None = None,
    tags: dict[str, str] | None = None,
) -> SendResult:
    context = dict(context or {})
    rendered = _render(template, context)
    to_list = [to] if isinstance(to, str) else list(to)
    idempotency_key = idempotency_key or f"cacop-{template}-{uuid4().hex[:12]}"

    tag_pairs = {"template": template, "org_id": org_id or "unknown"}
    tag_pairs.update({k: str(v) for k, v in (tags or {}).items()})

    params: dict[str, Any] = {
        "from": _from_address(),
        "to": to_list,
        "subject": rendered.subject,
        "html": rendered.html,
        "text": rendered.text,
        "headers": {"X-Entity-Ref-ID": idempotency_key},
        "tags": [{"name": k, "value": v[:63]} for k, v in tag_pairs.items()],
    }
    if reply_to:
        params["reply_to"] = reply_to

    if _dry_run():
        logger.info(
            "resend.dry_run to=%s template=%s subject=%r org=%s idem=%s",
            to_list, template, rendered.subject, org_id, idempotency_key,
        )
        return SendResult(id=idempotency_key, dry_run=True, template=template, subject=rendered.subject)

    _configure_sdk()
    if _resend_sdk is None:
        raise RuntimeError("resend SDK not installed")

    try:
        result = await asyncio.to_thread(_resend_sdk.Emails.send, params)
    except Exception as exc:
        logger.exception("resend.send failed template=%s to=%s: %s", template, to_list, exc)
        raise

    email_id = (result or {}).get("id") if isinstance(result, dict) else getattr(result, "id", None)
    logger.info("resend.sent id=%s template=%s to=%s org=%s", email_id, template, to_list, org_id)
    return SendResult(id=email_id or idempotency_key, dry_run=False, template=template, subject=rendered.subject)


async def send_batch(
    *,
    messages: Iterable[dict[str, Any]],
) -> list[SendResult]:
    """Send N templated emails in a single Resend batch call.

    `messages` items: {to, template, context, org_id?, tags?}
    """
    out: list[SendResult] = []
    for m in messages:
        out.append(await send_email(**m))
    return out


# ---------------------------------------------------------------------------
# Webhook signature verification (Svix)
# ---------------------------------------------------------------------------

def verify_webhook(raw_body: bytes, headers: dict[str, str]) -> dict[str, Any]:
    """Verify Resend/Svix webhook signature. Raises on failure. Returns parsed JSON."""
    secret = getattr(settings, "RESEND_WEBHOOK_SECRET", "") or ""
    if not secret:
        raise RuntimeError("RESEND_WEBHOOK_SECRET is not configured")
    from svix.webhooks import Webhook, WebhookVerificationError  # local import
    normalized = {
        "svix-id": headers.get("svix-id") or headers.get("Svix-Id") or "",
        "svix-timestamp": headers.get("svix-timestamp") or headers.get("Svix-Timestamp") or "",
        "svix-signature": headers.get("svix-signature") or headers.get("Svix-Signature") or "",
    }
    try:
        Webhook(secret).verify(raw_body, normalized)
    except WebhookVerificationError as exc:
        raise ValueError(f"Invalid webhook signature: {exc}") from exc
    return json.loads(raw_body.decode("utf-8"))
