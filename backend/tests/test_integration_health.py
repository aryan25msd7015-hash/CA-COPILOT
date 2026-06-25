import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.models.client import Client
from app.models.organization import Organization


def _database_available():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_integration_health_and_whatsapp_provider_event():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Integration Firm {suffix}"
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"integration-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        created = api.post("/clients", headers=headers, json={
            "name": "Integration Client",
            "entity_type": "pvt_ltd",
            "whatsapp_number": "+919999999999",
        })
        assert created.status_code == 201
        client_id = created.json()["id"]
        with SessionLocal() as db:
            client = db.query(Client).filter(Client.id == client_id).first()
            client.whatsapp_consent_at = datetime.now(timezone.utc)
            db.commit()

        health = api.get("/integrations/health", headers=headers)
        assert health.status_code == 200
        body = health.json()
        assert body["integrations"]["whatsapp"]["mode"] in {"development_fallback", "meta_business_api"}
        assert body["integrations"]["ocr"]["mode"] in {"local_placeholder", "azure_document_intelligence"}
        assert set(body["summary"].keys()) == {"ready", "degraded", "dev_fallback"}

        sent = api.post("/whatsapp/send-manual", headers=headers, json={
            "client_id": client_id,
            "message": "Please upload June purchase register.",
        })
        assert sent.status_code == 200
        assert sent.json()["status"] == "sent"

        events = api.get("/events?event_type=integration.whatsapp.message_sent", headers=headers)
        assert events.status_code == 200
        assert events.json()
        assert events.json()[0]["payload"]["template"] == "manual"

        after = api.get("/integrations/health", headers=headers)
        assert after.status_code == 200
        assert after.json()["integrations"]["whatsapp"]["messages_total"] >= 1
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
