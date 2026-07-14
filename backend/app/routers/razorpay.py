"""
FastAPI router — Razorpay endpoints.

Mounted at prefix `/razorpay` from app/main.py. In the Emergent Kubernetes
routing the ingress adds `/api` so browser URLs look like:

    POST  /api/razorpay/orders                    create Order (Checkout)
    POST  /api/razorpay/verify-payment            verify Checkout signature
    POST  /api/razorpay/payment-links             create standalone Payment Link
    POST  /api/razorpay/subscriptions             create SaaS Subscription
    DELETE /api/razorpay/subscriptions/{id}       cancel Subscription
    POST  /api/razorpay/webhook                   Razorpay -> us (signature checked)
    GET   /api/razorpay/config                    public bootstrap (key_id only)
    GET   /api/razorpay/plans                     hard-coded plan catalog

Security notes:
    • The KEY_SECRET is NEVER returned to the frontend.
    • Webhook verification uses razorpay.Utility HMAC-SHA256.
    • Every webhook is stored raw in razorpay_events for replay.
    • Idempotency: dedupe by (razorpay_event_id, event_type).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.razorpay_models import RazorpayEvent, RazorpaySubscription
from app.services import razorpay_service as rz
from app.utils.deps import require_user  # existing auth dep

router = APIRouter()
log = logging.getLogger("ca_platform.razorpay")


# ---------------------------------------------------------------------------
# Plan catalog — could easily move into DB later.
# ---------------------------------------------------------------------------

PLAN_CATALOG: list[dict[str, Any]] = [
    {
        "code": "starter",
        "name": "Starter",
        "tagline": "Solo & small practice — up to 25 clients",
        "amount_inr": 2499,
        "period": "monthly",
        "interval": 1,
        "features": [
            "GST reconciliation",
            "Deadlines & reminders",
            "Client portal (5 users)",
            "Basic AI review",
        ],
    },
    {
        "code": "pro",
        "name": "Pro",
        "tagline": "Growing firm — up to 150 clients",
        "amount_inr": 5999,
        "period": "monthly",
        "interval": 1,
        "features": [
            "Everything in Starter",
            "Exception Autopilot",
            "Notice drafter + certificates",
            "WhatsApp collections",
        ],
    },
    {
        "code": "enterprise",
        "name": "Enterprise",
        "tagline": "Full command deck — unlimited clients",
        "amount_inr": 14999,
        "period": "monthly",
        "interval": 1,
        "features": [
            "Everything in Pro",
            "Benchmarking + RFP",
            "Audit papers + Ind AS 116",
            "SSO + priority support",
        ],
    },
]


@router.get("/config")
def public_config():
    """Bootstrap data the frontend needs to open Checkout. Secret NEVER exposed."""
    return {
        "key_id": settings.RAZORPAY_KEY_ID or "",
        "configured": rz.is_configured(),
        "webhook_configured": bool(settings.RAZORPAY_WEBHOOK_SECRET),
        "currency": "INR",
        "test_mode": bool(settings.RAZORPAY_KEY_ID.startswith("rzp_test_")),
    }


@router.get("/plans")
def plans():
    return PLAN_CATALOG


# ---------------------------------------------------------------------------
# 1) One-time payment (Orders API)
# ---------------------------------------------------------------------------

class OrderIn(BaseModel):
    amount_inr: float = Field(gt=0)
    receipt: str = Field(min_length=1, max_length=40)
    invoice_id: str | None = None
    client_id: str | None = None
    description: str | None = None


class VerifyIn(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    invoice_id: str | None = None


@router.post("/orders")
def create_order(body: OrderIn, user=Depends(require_user)):
    if not rz.is_configured():
        raise HTTPException(503, "Razorpay is not configured")
    notes = {"org_id": str(user.org_id), "user_id": str(user.id)}
    if body.invoice_id: notes["invoice_id"] = body.invoice_id
    if body.client_id: notes["client_id"] = body.client_id
    if body.description: notes["description"] = body.description[:200]
    try:
        order = rz.create_order(
            amount_inr=body.amount_inr,
            receipt=body.receipt,
            notes=notes,
        )
    except rz.RazorpayError as exc:
        raise HTTPException(502, str(exc))
    return {
        "order_id": order["id"],
        "amount_paise": order["amount"],
        "currency": order["currency"],
        "receipt": order.get("receipt"),
        "key_id": settings.RAZORPAY_KEY_ID,
        "notes": order.get("notes") or {},
    }


@router.post("/verify-payment")
def verify_payment(body: VerifyIn, db: Session = Depends(get_db), user=Depends(require_user)):
    try:
        rz.verify_checkout_signature(
            razorpay_order_id=body.razorpay_order_id,
            razorpay_payment_id=body.razorpay_payment_id,
            razorpay_signature=body.razorpay_signature,
        )
    except rz.RazorpayError as exc:
        raise HTTPException(400, str(exc))

    # If this order paid an invoice, mark the invoice paid via the existing
    # practice_ops mutation (kept loose to avoid a hard import cycle).
    if body.invoice_id:
        try:
            from app.models.practice_ops import Invoice, InvoicePayment  # local import
            inv = db.query(Invoice).filter(Invoice.id == body.invoice_id,
                                           Invoice.org_id == user.org_id).first()
            if inv:
                fetched = rz.fetch_payment(body.razorpay_payment_id)
                amount = float(fetched.get("amount") or 0) / 100
                db.add(InvoicePayment(
                    invoice_id=inv.id,
                    org_id=inv.org_id,
                    amount=amount,
                    paid_at=datetime.now(timezone.utc),
                    mode="razorpay",
                    reference=body.razorpay_payment_id,
                ))
                inv.amount_paid = float(inv.amount_paid or 0) + amount
                if inv.amount_paid >= float(inv.total or 0):
                    inv.status = "paid"
                else:
                    inv.status = "part_paid"
                db.commit()
        except Exception as exc:                           # noqa: BLE001 — best-effort
            log.exception("verify_payment: invoice reconcile failed: %s", exc)

    return {"ok": True, "verified": True}


# ---------------------------------------------------------------------------
# 2) Subscription flow
# ---------------------------------------------------------------------------

class SubscriptionIn(BaseModel):
    plan_code: str
    total_count: int = 12


@router.post("/subscriptions")
def start_subscription(body: SubscriptionIn, db: Session = Depends(get_db), user=Depends(require_user)):
    if not rz.is_configured():
        raise HTTPException(503, "Razorpay is not configured")
    plan_def = next((p for p in PLAN_CATALOG if p["code"] == body.plan_code), None)
    if not plan_def:
        raise HTTPException(404, "Unknown plan_code")

    try:
        plan = rz.create_plan(
            period=plan_def["period"],
            interval=plan_def["interval"],
            item_name=f"CA Copilot · {plan_def['name']}",
            amount_inr=plan_def["amount_inr"],
            description=plan_def["tagline"],
            notes={"org_id": str(user.org_id), "plan_code": plan_def["code"]},
        )
        sub = rz.create_subscription(
            plan_id=plan["id"],
            total_count=body.total_count,
            notes={"org_id": str(user.org_id), "plan_code": plan_def["code"]},
        )
    except rz.RazorpayError as exc:
        raise HTTPException(502, str(exc))

    row = RazorpaySubscription(
        org_id=user.org_id,
        razorpay_plan_id=plan["id"],
        razorpay_subscription_id=sub["id"],
        plan_code=plan_def["code"],
        plan_period=plan_def["period"],
        amount_inr=plan_def["amount_inr"],
        status=sub.get("status") or "created",
        short_url=sub.get("short_url"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "razorpay_subscription_id": sub["id"],
        "short_url": sub.get("short_url"),
        "status": row.status,
        "plan_code": row.plan_code,
    }


@router.delete("/subscriptions/{sub_id}")
def cancel_sub(sub_id: str, db: Session = Depends(get_db), user=Depends(require_user)):
    row = db.query(RazorpaySubscription).filter(
        RazorpaySubscription.id == sub_id,
        RazorpaySubscription.org_id == user.org_id,
    ).first()
    if not row:
        raise HTTPException(404, "Subscription not found")
    try:
        rz.cancel_subscription(row.razorpay_subscription_id, cancel_at_cycle_end=True)
    except rz.RazorpayError as exc:
        raise HTTPException(502, str(exc))
    row.status = "cancelled"
    row.ended_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "id": row.id, "status": row.status}


@router.get("/subscriptions")
def list_subs(db: Session = Depends(get_db), user=Depends(require_user)):
    rows = (
        db.query(RazorpaySubscription)
        .filter(RazorpaySubscription.org_id == user.org_id)
        .order_by(RazorpaySubscription.created_at.desc())
        .all()
    )
    return [{
        "id": r.id,
        "plan_code": r.plan_code,
        "amount_inr": float(r.amount_inr),
        "currency": r.currency,
        "status": r.status,
        "short_url": r.short_url,
        "next_charge_at": r.next_charge_at.isoformat() if r.next_charge_at else None,
        "created_at": r.created_at.isoformat(),
    } for r in rows]


# ---------------------------------------------------------------------------
# 3) Standalone payment links (ad-hoc, no invoice row)
# ---------------------------------------------------------------------------

class PaymentLinkIn(BaseModel):
    amount_inr: float = Field(gt=0)
    description: str
    customer_name: str
    customer_email: str | None = None
    customer_contact: str | None = None
    reference_id: str | None = None
    expire_in_days: int = 7


@router.post("/payment-links")
def payment_link(body: PaymentLinkIn, user=Depends(require_user)):
    if not rz.is_configured():
        raise HTTPException(503, "Razorpay is not configured")
    try:
        link = rz.create_standalone_payment_link(
            amount_inr=body.amount_inr,
            description=body.description,
            customer_name=body.customer_name,
            customer_email=body.customer_email,
            customer_contact=body.customer_contact,
            reference_id=body.reference_id,
            expire_in_days=body.expire_in_days,
            notes={"org_id": str(user.org_id)},
        )
    except rz.RazorpayError as exc:
        raise HTTPException(502, str(exc))
    return {
        "id": link.get("id"),
        "short_url": link.get("short_url"),
        "amount_inr": body.amount_inr,
        "status": link.get("status"),
    }


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------

@router.post("/webhook", include_in_schema=False)
async def webhook(
    request: Request,
    db: Session = Depends(get_db),
    x_razorpay_signature: str | None = Header(default=None, alias="X-Razorpay-Signature"),
    x_razorpay_event_id: str | None = Header(default=None, alias="X-Razorpay-Event-Id"),
):
    raw = await request.body()
    signature_ok = False
    try:
        signature_ok = rz.verify_webhook_signature(raw, x_razorpay_signature or "")
    except rz.RazorpayError:
        signature_ok = False
    if not signature_ok:
        # Do NOT 4xx before persisting the raw body for later replay if you want,
        # but Razorpay retries on 5xx / 4xx.
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad signature")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        raise HTTPException(400, "Invalid JSON")

    summary = rz.summarize_event(payload)

    # Idempotency dedupe
    if x_razorpay_event_id:
        existing = (
            db.query(RazorpayEvent)
            .filter(RazorpayEvent.razorpay_event_id == x_razorpay_event_id)
            .first()
        )
        if existing:
            return {"ok": True, "deduped": True}

    row = RazorpayEvent(
        org_id=summary.get("org_id"),
        razorpay_event_id=x_razorpay_event_id,
        event_type=summary["event"] or "unknown",
        signature_ok="true",
        payload=payload,
        razorpay_order_id=summary.get("razorpay_order_id"),
        razorpay_payment_id=summary.get("razorpay_payment_id"),
        razorpay_payment_link_id=summary.get("razorpay_payment_link_id"),
        razorpay_subscription_id=summary.get("razorpay_subscription_id"),
        razorpay_refund_id=summary.get("razorpay_refund_id"),
        invoice_id=summary.get("invoice_id"),
    )
    db.add(row)
    db.commit()

    # Reduce known events into domain state (best-effort; failures are logged
    # but don't fail the webhook so Razorpay doesn't retry endlessly).
    try:
        _reduce_event(db, summary)
        row.handled_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        row.handle_error = str(exc)[:500]
        log.exception("webhook.reduce_failed event=%s: %s", summary.get("event"), exc)
    finally:
        db.commit()

    return {"ok": True, "event": summary["event"]}


def _reduce_event(db: Session, s: dict[str, Any]) -> None:
    """Fold a webhook summary into invoice / subscription tables."""
    event = s.get("event") or ""
    # Subscription lifecycle
    if event.startswith("subscription.") and s.get("razorpay_subscription_id"):
        sub = (
            db.query(RazorpaySubscription)
            .filter(RazorpaySubscription.razorpay_subscription_id == s["razorpay_subscription_id"])
            .first()
        )
        if sub:
            status_map = {
                "subscription.activated": "active",
                "subscription.charged": "active",
                "subscription.halted": "halted",
                "subscription.cancelled": "cancelled",
                "subscription.completed": "completed",
            }
            new_status = status_map.get(event)
            if new_status:
                sub.status = new_status
                if new_status in ("cancelled", "completed"):
                    sub.ended_at = datetime.now(timezone.utc)
        return

    # Invoice payment via order.paid / payment.captured
    if event in ("order.paid", "payment.captured", "payment_link.paid") and s.get("invoice_id"):
        try:
            from app.models.practice_ops import Invoice, InvoicePayment
            inv = db.query(Invoice).filter(Invoice.id == s["invoice_id"]).first()
            if inv and s.get("amount_inr"):
                already = (
                    db.query(InvoicePayment)
                    .filter(InvoicePayment.reference == s.get("razorpay_payment_id"))
                    .first()
                )
                if not already:
                    db.add(InvoicePayment(
                        invoice_id=inv.id,
                        org_id=inv.org_id,
                        amount=s["amount_inr"],
                        paid_at=datetime.now(timezone.utc),
                        mode="razorpay",
                        reference=s.get("razorpay_payment_id") or s.get("razorpay_payment_link_id"),
                    ))
                    inv.amount_paid = float(inv.amount_paid or 0) + float(s["amount_inr"])
                    inv.status = "paid" if inv.amount_paid >= float(inv.total or 0) else "part_paid"
        except Exception:
            pass
