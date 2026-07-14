import uuid
from datetime import date

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
def test_autopilot_tally_sync_exception_followup_and_review():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Autopilot Integration {suffix}"
    headers = {}
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"autopilot-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        client = api.post("/clients", headers=headers, json={
            "name": "Autopilot Manufacturing Pvt Ltd",
            "gstin": "27ABCDE1234F1Z5",
            "whatsapp_number": "919999999999",
        })
        assert client.status_code == 201
        client_id = client.json()["id"]

        sync = api.post("/autopilot/tally/sync", headers=headers, json={
            "client_id": client_id,
            "source_name": "Integration Tally",
            "period": "2026-06",
            "records": [{
                "Voucher No": f"PUR-{suffix[:6]}",
                "Date": date.today().strftime("%d/%m/%Y"),
                "Party Name": "Threshold Supplier Pvt Ltd",
                "GSTIN/UIN of Party": "27AAACT1111A1Z1",
                "Amount": "49,500",
                "Tax Amount": "8,910",
            }],
        })
        assert sync.status_code == 201
        assert sync.json()["sync_run"]["records_imported"] == 1

        exceptions = api.get("/autopilot/exceptions?source_type=tally_transaction", headers=headers)
        assert exceptions.status_code == 200
        assert exceptions.json()
        exception_id = exceptions.json()[0]["id"]
        assert exceptions.json()[0]["severity"] in {"medium", "high"}

        followup = api.post("/autopilot/followups", headers=headers, json={
            "exception_id": exception_id,
            "message": "Please share voucher support for the threshold invoice.",
        })
        assert followup.status_code == 201
        assert followup.json()["status"] == "draft"

        reviewed = api.patch(f"/autopilot/exceptions/{exception_id}", headers=headers, json={
            "status": "resolved",
            "action_type": "ca_conclusion",
            "notes": "Voucher verified against supporting documents.",
        })
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "resolved"

        overview = api.get("/autopilot/overview?auto_refresh=false", headers=headers)
        assert overview.status_code == 200
        assert "summary" in overview.json()
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
            db.commit()
