import hashlib
import hmac
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.organization import Organization


def _database_available():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_signed_razorpay_webhook_records_payment_once(monkeypatch):
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Gateway Firm {suffix}"
    monkeypatch.setattr(settings, "RAZORPAY_WEBHOOK_SECRET", "webhook-test-secret")
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"gateway-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        client = api.post("/clients", headers=headers, json={
            "name": "Gateway Client",
            "entity_type": "pvt_ltd",
            "email": "payer@example.com",
        })
        assert client.status_code == 201

        invoice = api.post("/billing/invoices", headers=headers, json={
            "client_id": client.json()["id"],
            "line_items": [{"description": "Monthly fees", "amount": 1000}],
            "tax_rate": 18,
            "status": "sent",
        })
        assert invoice.status_code == 201
        invoice_id = invoice.json()["id"]

        payload = {
            "event": "payment_link.paid",
            "payload": {
                "payment_link": {
                    "entity": {
                        "id": "plink_test",
                        "amount_paid": 118000,
                        "status": "paid",
                        "notes": {
                            "org_id": "",
                            "invoice_id": invoice_id,
                            "client_id": client.json()["id"],
                        },
                    },
                },
                "payment": {
                    "entity": {
                        "id": "pay_test_once",
                        "amount": 118000,
                        "method": "upi",
                        "status": "captured",
                    },
                },
            },
        }
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            payload["payload"]["payment_link"]["entity"]["notes"]["org_id"] = str(org.id)
        raw = json.dumps(payload, separators=(",", ":")).encode()
        signature = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()

        recorded = api.post(
            "/billing/webhooks/razorpay",
            content=raw,
            headers={"x-razorpay-signature": signature, "content-type": "application/json"},
        )
        assert recorded.status_code == 200
        assert recorded.json()["status"] == "recorded"

        duplicate = api.post(
            "/billing/webhooks/razorpay",
            content=raw,
            headers={"x-razorpay-signature": signature, "content-type": "application/json"},
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "duplicate_ignored"

        updated = api.get("/billing/invoices", headers=headers)
        paid = [row for row in updated.json() if row["id"] == invoice_id][0]
        assert paid["status"] == "paid"
        assert paid["amount_paid"] == 1180
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
