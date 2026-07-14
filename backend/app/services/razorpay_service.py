"""
Razorpay integration — extends the existing payment_gateway module with the
three flows requested by the CA Copilot billing team:

    1. One-time invoice payments via Orders API + hosted Razorpay Checkout
       (server creates order, frontend opens Checkout modal, server verifies
       the returned signature and marks the invoice paid).

    2. Subscription billing — Plans + Subscriptions (CA firm subscribes to
       Starter / Pro / Enterprise plans on CA Copilot).

    3. Payment Links — server-side "share a pay link" without needing an
       Invoice row (for ad-hoc collections). This complements the existing
       invoice-scoped payment_gateway.create_payment_link().

All three use the official `razorpay` Python SDK (razorpay==2.0.1). Amounts are
handled in **paise** at the SDK boundary; the rest of the codebase uses INR.

Signatures (HMAC-SHA256) for both the Checkout callback and Webhooks are
verified via `razorpay.Utility` — never trusted from the client.

Env vars (backend/.env, never leak to frontend):
    RAZORPAY_KEY_ID
    RAZORPAY_KEY_SECRET
    RAZORPAY_WEBHOOK_SECRET

The public key id is exposed to the frontend via NEXT_PUBLIC_RAZORPAY_KEY_ID.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import razorpay
from razorpay.errors import BadRequestError, ServerError, SignatureVerificationError

from app.config import settings

logger = logging.getLogger("ca_platform.razorpay")


class RazorpayError(RuntimeError):
    """Raised when Razorpay rejects a request or the SDK is misconfigured."""


# ---------------------------------------------------------------------------
# SDK client (lazy — do not instantiate at import time so app can boot without
# real keys during local dev / preview).
# ---------------------------------------------------------------------------

def _client() -> razorpay.Client:
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RazorpayError(
            "RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET must be set in backend/.env"
        )
    c = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    c.set_app_details({"title": "CA Copilot", "version": "1.0.0"})
    return c


def is_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


# ---------------------------------------------------------------------------
# 1) Orders API — power the embedded Checkout modal
# ---------------------------------------------------------------------------

def create_order(
    *,
    amount_inr: float,
    currency: str = "INR",
    receipt: str,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create a Razorpay Order. `amount_inr` is in rupees; converted to paise here.

    `receipt` MUST be ≤ 40 characters (Razorpay hard limit).
    """
    if amount_inr <= 0:
        raise RazorpayError("Order amount must be > 0")
    payload = {
        "amount": int(round(amount_inr * 100)),
        "currency": currency,
        "receipt": receipt[:40],
        "payment_capture": 1,   # auto-capture on success
        "notes": {k: str(v) for k, v in (notes or {}).items()},
    }
    try:
        order = _client().order.create(data=payload)
    except (BadRequestError, ServerError) as exc:
        raise RazorpayError(f"Razorpay order create failed: {exc}") from exc
    logger.info("razorpay.order.created id=%s receipt=%s amount=%s",
                order.get("id"), receipt, payload["amount"])
    return order


def verify_checkout_signature(
    *,
    razorpay_order_id: str,
    razorpay_payment_id: str,
    razorpay_signature: str,
) -> bool:
    """Called from the frontend Checkout `handler` callback → POSTed to backend
    → we verify with the SDK. Returns True on success, raises on failure."""
    try:
        _client().utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
        return True
    except SignatureVerificationError as exc:
        logger.warning("razorpay.signature.invalid order=%s payment=%s",
                       razorpay_order_id, razorpay_payment_id)
        raise RazorpayError("Payment signature verification failed") from exc


def fetch_payment(payment_id: str) -> dict[str, Any]:
    try:
        return _client().payment.fetch(payment_id)
    except (BadRequestError, ServerError) as exc:
        raise RazorpayError(f"Fetch payment failed: {exc}") from exc


# ---------------------------------------------------------------------------
# 2) Subscriptions — plans + subscriptions
# ---------------------------------------------------------------------------

def create_plan(
    *,
    period: str,               # 'daily' | 'weekly' | 'monthly' | 'yearly'
    interval: int,             # billing interval (e.g. 1 = every month)
    item_name: str,
    amount_inr: float,
    currency: str = "INR",
    description: str = "",
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "period": period,
        "interval": interval,
        "item": {
            "name": item_name[:80],
            "amount": int(round(amount_inr * 100)),
            "currency": currency,
            "description": description[:255],
        },
        "notes": {k: str(v) for k, v in (notes or {}).items()},
    }
    try:
        return _client().plan.create(data=payload)
    except (BadRequestError, ServerError) as exc:
        raise RazorpayError(f"Plan create failed: {exc}") from exc


def create_subscription(
    *,
    plan_id: str,
    total_count: int = 12,
    customer_notify: bool = True,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "plan_id": plan_id,
        "total_count": total_count,
        "customer_notify": 1 if customer_notify else 0,
        "notes": {k: str(v) for k, v in (notes or {}).items()},
    }
    try:
        return _client().subscription.create(data=payload)
    except (BadRequestError, ServerError) as exc:
        raise RazorpayError(f"Subscription create failed: {exc}") from exc


def cancel_subscription(subscription_id: str, cancel_at_cycle_end: bool = True) -> dict[str, Any]:
    try:
        return _client().subscription.cancel(
            subscription_id,
            {"cancel_at_cycle_end": 1 if cancel_at_cycle_end else 0},
        )
    except (BadRequestError, ServerError) as exc:
        raise RazorpayError(f"Subscription cancel failed: {exc}") from exc


# ---------------------------------------------------------------------------
# 3) Standalone Payment Links (ad-hoc, no invoice row required)
# ---------------------------------------------------------------------------

def create_standalone_payment_link(
    *,
    amount_inr: float,
    description: str,
    customer_name: str,
    customer_email: str | None = None,
    customer_contact: str | None = None,
    reference_id: str | None = None,
    expire_in_days: int = 7,
    notes: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload = {
        "amount": int(round(amount_inr * 100)),
        "currency": "INR",
        "accept_partial": False,
        "expire_by": int(
            (datetime.now(timezone.utc) + timedelta(days=expire_in_days)).timestamp()
        ),
        "reference_id": (reference_id or f"cacop-{int(datetime.now().timestamp())}")[:40],
        "description": description[:2048],
        "customer": {
            "name": customer_name,
            "email": customer_email or None,
            "contact": customer_contact or None,
        },
        "notify": {"sms": bool(customer_contact), "email": bool(customer_email)},
        "reminder_enable": True,
        "notes": {k: str(v) for k, v in (notes or {}).items()},
    }
    try:
        return _client().payment_link.create(data=payload)
    except (BadRequestError, ServerError) as exc:
        raise RazorpayError(f"Payment link create failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Webhook helpers — verify + normalize
# ---------------------------------------------------------------------------

# Events we care about. Feel free to subscribe to all in the Razorpay dashboard;
# unknown events will simply be logged and stored as raw for later replay.
WEBHOOK_EVENTS = frozenset({
    "payment.captured",
    "payment.failed",
    "refund.processed",
    "refund.failed",
    "payment_link.paid",
    "payment_link.expired",
    "payment_link.cancelled",
    "subscription.activated",
    "subscription.charged",
    "subscription.halted",
    "subscription.cancelled",
    "subscription.completed",
    "order.paid",
})


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """HMAC-SHA256 verification via the SDK utility (constant-time compare)."""
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise RazorpayError("RAZORPAY_WEBHOOK_SECRET is not configured")
    try:
        _client().utility.verify_webhook_signature(
            raw_body.decode("utf-8") if isinstance(raw_body, bytes) else raw_body,
            signature,
            settings.RAZORPAY_WEBHOOK_SECRET,
        )
        return True
    except SignatureVerificationError:
        return False


def summarize_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a webhook payload into the fields the app cares about."""
    inner = (payload.get("payload") or {})
    payment = ((inner.get("payment") or {}).get("entity")) or {}
    order = ((inner.get("order") or {}).get("entity")) or {}
    link = ((inner.get("payment_link") or {}).get("entity")) or {}
    sub = ((inner.get("subscription") or {}).get("entity")) or {}
    refund = ((inner.get("refund") or {}).get("entity")) or {}
    notes = payment.get("notes") or link.get("notes") or order.get("notes") or sub.get("notes") or {}
    amount_paise = (
        payment.get("amount")
        or link.get("amount_paid")
        or order.get("amount_paid")
        or refund.get("amount")
        or 0
    )
    return {
        "event_id": payload.get("id"),
        "event": payload.get("event"),
        "created_at": payload.get("created_at"),
        "razorpay_order_id": payment.get("order_id") or order.get("id"),
        "razorpay_payment_id": payment.get("id"),
        "razorpay_payment_link_id": link.get("id"),
        "razorpay_subscription_id": sub.get("id"),
        "razorpay_refund_id": refund.get("id"),
        "amount_inr": round(float(amount_paise or 0) / 100, 2),
        "currency": payment.get("currency") or link.get("currency") or "INR",
        "status": payment.get("status") or link.get("status") or sub.get("status"),
        "method": payment.get("method"),
        "email": payment.get("email"),
        "contact": payment.get("contact"),
        "org_id": notes.get("org_id"),
        "client_id": notes.get("client_id"),
        "invoice_id": notes.get("invoice_id"),
        "raw": payload,
    }
