import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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
def test_system_events_are_recorded_listed_and_dispatched():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Events Firm {suffix}"
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"events-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        created = api.post("/clients", headers=headers, json={
            "name": "Event Ledger Client",
            "entity_type": "pvt_ltd",
        })
        assert created.status_code == 201
        client_id = created.json()["id"]

        updated = api.patch(f"/clients/{client_id}", headers=headers, json={"industry": "Manufacturing"})
        assert updated.status_code == 200

        listed = api.get("/events", headers=headers)
        assert listed.status_code == 200
        event_types = [row["event_type"] for row in listed.json()]
        assert "organization.initialized" in event_types
        assert "client.created" in event_types
        assert "client.updated" in event_types

        client_events = api.get(
            f"/events?aggregate_type=client&aggregate_id={client_id}",
            headers=headers,
        )
        assert client_events.status_code == 200
        assert {row["event_type"] for row in client_events.json()} >= {"client.created", "client.updated"}

        summary = api.get("/events/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["total_events"] >= 3
        assert summary.json()["by_type"]["client.created"] == 1

        event_id = next(row["id"] for row in client_events.json() if row["event_type"] == "client.created")
        dispatched = api.post(f"/events/{event_id}/dispatch", headers=headers)
        assert dispatched.status_code == 200
        assert dispatched.json()["status"] == "dispatched"
        assert dispatched.json()["dispatch_attempts"] == 1
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
