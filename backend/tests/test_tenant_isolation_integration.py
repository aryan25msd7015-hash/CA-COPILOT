import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.engines.automation_engines import month_period
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
def test_api_tenant_isolation():
    client = TestClient(app)
    suffix = uuid.uuid4().hex
    org_names = [f"Isolation A {suffix}", f"Isolation B {suffix}"]
    tokens = []
    ids = []
    try:
        for index, org_name in enumerate(org_names):
            response = client.post("/auth/register", json={
                "org_name": org_name,
                "email": f"isolation-{index}-{suffix}@example.com",
                "password": "StrongPass123!",
            })
            assert response.status_code == 201
            tokens.append(response.json()["access_token"])

        for index, token in enumerate(tokens):
            response = client.post("/clients", headers={"Authorization": f"Bearer {token}"}, json={"name": f"Tenant {index} client"})
            assert response.status_code == 201
            ids.append(response.json()["id"])

        for index, token in enumerate(tokens):
            headers = {"Authorization": f"Bearer {token}"}
            visible = client.get("/clients", headers=headers).json()
            assert [row["id"] for row in visible] == [ids[index]]
            assert "benchmark_consent_at" in visible[0]
            assert "whatsapp_consent_at" in visible[0]
            assert client.get(f"/clients/{ids[1 - index]}", headers=headers).status_code == 404

            calendar = client.get(f"/calendar/GSTR1/{month_period()}/clients", headers=headers)
            assert calendar.status_code == 200
            assert [row["client_id"] for row in calendar.json()] == [ids[index]]

            other_calendar = client.get(
                f"/calendar/GSTR1/{month_period()}/clients",
                headers={"Authorization": f"Bearer {tokens[1 - index]}"},
            ).json()
            assert client.patch(
                f"/calendar/items/{other_calendar[0]['id']}",
                headers=headers,
                json={"data_received": True},
            ).status_code == 404
    finally:
        with SessionLocal() as db:
            for org_name in org_names:
                org = db.query(Organization).filter(Organization.name == org_name).first()
                if org:
                    db.delete(org)
            db.commit()
