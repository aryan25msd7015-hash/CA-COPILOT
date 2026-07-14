"""Transactional email delivery for auth and account workflows.

For Resend delivery (preferred), see `app/services/resend_service.py`. When the
Resend API key is set (and not a placeholder), the send helpers below route
through Resend's HUD-branded templates instead of legacy SMTP.
"""
from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from app.config import settings
from app.services import resend_service as rs


class EmailDeliveryError(RuntimeError):
    """Raised when a configured email provider cannot deliver a message."""


def email_provider_status() -> dict:
    if _resend_active():
        return {
            "provider": "resend",
            "configured": True,
            "mode": "resend_dry_run" if rs._dry_run() else "resend",
            "from": rs._from_address(),
        }
    configured = _smtp_configured()
    provider = settings.EMAIL_PROVIDER.lower()
    return {
        "provider": provider,
        "configured": configured if provider == "smtp" else False,
        "mode": "smtp" if provider == "smtp" and configured else "development_response",
        "from": settings.EMAIL_FROM,
    }


def _resend_active() -> bool:
    """True if Resend is configured OR intentionally in dry-run mode."""
    key = (settings.RESEND_API_KEY or "").strip()
    return bool(key) or bool(getattr(settings, "RESEND_DRY_RUN", False))


def _send_resend(*, template: str, to_email: str, context: dict) -> dict:
    """Blocking wrapper around the async resend send helper so the existing
    email_service call-sites (which are synchronous) can continue to work."""
    try:
        result = asyncio.run(rs.send_email(
            to=to_email, template=template, context=context,
        ))
    except RuntimeError:
        # If we're already inside a running loop, hop threads.
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(rs.send_email(
                to=to_email, template=template, context=context,
            ))
        finally:
            loop.close()
    return {
        "delivered": not result.dry_run,
        "mode": "resend_dry_run" if result.dry_run else "resend",
        "message_id": result.id,
        "template": result.template,
    }


def assert_email_ready_for_production() -> None:
    if settings.ENV == "production":
        if _resend_active() and not rs._dry_run():
            return
        if not _smtp_configured():
            raise EmailDeliveryError("Email delivery is not configured")


def send_password_reset_email(to_email: str, token: str) -> dict:
    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    if _resend_active():
        return _send_resend(template="password_reset", to_email=to_email, context={
            "cta_url": link,
            "meta": [
                ("Recipient", to_email),
                ("Expires in", f"{settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes"),
            ],
        })
    subject = "Reset your CA Copilot password"
    text = (
        "We received a request to reset your CA Copilot password.\n\n"
        f"Open this link to set a new password: {link}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes. "
        "If you did not request this, you can ignore this email."
    )
    html = _button_email(
        title="Reset your password",
        intro="Use the secure link below to set a new CA Copilot password.",
        button_label="Reset password",
        button_url=link,
        footer=f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes.",
    )
    return _send(to_email, subject, text, html)


def send_email_verification_email(to_email: str, token: str) -> dict:
    link = f"{settings.FRONTEND_URL.rstrip('/')}/verify-email?token={token}"
    if _resend_active():
        return _send_resend(template="email_verification", to_email=to_email, context={
            "cta_url": link,
            "meta": [
                ("Recipient", to_email),
                ("Expires in", f"{settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours"),
            ],
        })
    subject = "Verify your CA Copilot email"
    text = (
        "Please verify this email address for CA Copilot.\n\n"
        f"Open this link to verify your account: {link}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours."
    )
    html = _button_email(
        title="Verify your email",
        intro="Confirm this address so security alerts and account recovery work correctly.",
        button_label="Verify email",
        button_url=link,
        footer=f"This link expires in {settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS} hours.",
    )
    return _send(to_email, subject, text, html)


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_USERNAME and settings.SMTP_PASSWORD)


def _send(to_email: str, subject: str, text: str, html: str) -> dict:
    provider = settings.EMAIL_PROVIDER.lower()
    if provider != "smtp":
        if settings.ENV == "production":
            raise EmailDeliveryError("EMAIL_PROVIDER must be smtp in production")
        return {"delivered": False, "mode": "development_response", "provider": provider}
    if not _smtp_configured():
        raise EmailDeliveryError("SMTP_HOST, SMTP_USERNAME and SMTP_PASSWORD are required")

    from_name, from_addr = parseaddr(settings.EMAIL_FROM)
    if not from_addr:
        from_addr = settings.SMTP_USERNAME
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((from_name or "CA Copilot", from_addr))
    message["To"] = to_email
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        if settings.SMTP_USE_SSL:
            smtp = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        else:
            smtp = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
        with smtp:
            if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
                smtp.starttls()
            smtp.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            smtp.send_message(message)
    except Exception as exc:
        raise EmailDeliveryError(f"SMTP delivery failed: {exc}") from exc
    return {"delivered": True, "mode": "smtp", "provider": "smtp"}


def _button_email(title: str, intro: str, button_label: str, button_url: str, footer: str) -> str:
    return f"""<!doctype html>
<html>
<body style="font-family:Arial,sans-serif;background:#f6f8fb;margin:0;padding:32px;color:#0f172a">
  <div style="max-width:560px;margin:auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:28px">
    <h1 style="font-size:22px;margin:0 0 12px">{title}</h1>
    <p style="font-size:15px;line-height:1.5;margin:0 0 24px">{intro}</p>
    <p style="margin:0 0 24px">
      <a href="{button_url}" style="background:#0f172a;color:#ffffff;text-decoration:none;padding:12px 18px;border-radius:8px;display:inline-block">{button_label}</a>
    </p>
    <p style="font-size:12px;line-height:1.5;color:#64748b;margin:0">{footer}</p>
  </div>
</body>
</html>"""
