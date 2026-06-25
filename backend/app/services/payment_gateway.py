"""Payment gateway adapters for practice billing."""
from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from app.config import settings


class PaymentGatewayError(RuntimeError):
    """Raised when a payment gateway is not configured or rejects a request."""


def payment_gateway_status() -> dict:
    provider = settings.PAYMENT_PROVIDER.lower()
    razorpay_ready = bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)
    return {
        "provider": provider,
        "configured": provider == "razorpay" and razorpay_ready,
        "webhook_configured": bool(settings.RAZORPAY_WEBHOOK_SECRET),
        "mode": "razorpay" if provider == "razorpay" and razorpay_ready else "manual_collection",
    }


def create_payment_link(invoice, client, org) -> dict[str, Any]:
    if settings.PAYMENT_PROVIDER.lower() != "razorpay":
        raise PaymentGatewayError("PAYMENT_PROVIDER must be razorpay to generate checkout links")
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise PaymentGatewayError("Razorpay key id and secret are required")
    balance = max(float(invoice.total or 0) - float(invoice.amount_paid or 0), 0)
    if balance <= 0:
        raise PaymentGatewayError("Invoice is already paid")
    payload = {
        "amount": int(round(balance * 100)),
        "currency": "INR",
        "accept_partial": False,
        "expire_by": int((datetime.now(timezone.utc) + timedelta(days=settings.PAYMENT_LINK_EXPIRE_DAYS)).timestamp()),
        "reference_id": invoice.invoice_no,
        "description": f"CA Copilot invoice {invoice.invoice_no}",
        "customer": {
            "name": client.name,
            "email": client.email or None,
            "contact": client.whatsapp_number or None,
        },
        "notify": {"sms": False, "email": bool(client.email)},
        "reminder_enable": True,
        "notes": {
            "org_id": str(invoice.org_id),
            "client_id": str(invoice.client_id),
            "invoice_id": str(invoice.id),
            "invoice_no": invoice.invoice_no,
            "org_name": getattr(org, "name", ""),
        },
    }
    response = requests.post(
        "https://api.razorpay.com/v1/payment_links",
        json=payload,
        headers={
            "Authorization": f"Basic {_basic_auth()}",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if response.status_code >= 400:
        raise PaymentGatewayError(f"Razorpay payment link failed: {response.text[:300]}")
    data = response.json()
    return {
        "provider": "razorpay",
        "provider_reference": data.get("id"),
        "payment_link": data.get("short_url") or data.get("callback_url"),
        "status": data.get("status"),
        "raw": data,
    }


def verify_razorpay_webhook(raw_body: bytes, signature: str | None) -> bool:
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise PaymentGatewayError("Razorpay webhook secret is not configured")
    if not signature:
        return False
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_razorpay_payment_event(payload: dict[str, Any]) -> dict[str, Any]:
    payment_link = ((payload.get("payload") or {}).get("payment_link") or {}).get("entity") or {}
    payment = ((payload.get("payload") or {}).get("payment") or {}).get("entity") or {}
    notes = payment.get("notes") or payment_link.get("notes") or {}
    amount_paise = payment.get("amount") or payment_link.get("amount_paid") or 0
    return {
        "event": payload.get("event"),
        "invoice_id": notes.get("invoice_id"),
        "org_id": notes.get("org_id"),
        "client_id": notes.get("client_id"),
        "amount": round(float(amount_paise or 0) / 100, 2),
        "payment_id": payment.get("id") or payment_link.get("id"),
        "payment_link_id": payment_link.get("id"),
        "status": payment.get("status") or payment_link.get("status"),
        "method": payment.get("method") or "razorpay",
        "raw": payload,
    }


def _basic_auth() -> str:
    token = f"{settings.RAZORPAY_KEY_ID}:{settings.RAZORPAY_KEY_SECRET}".encode()
    return base64.b64encode(token).decode()
