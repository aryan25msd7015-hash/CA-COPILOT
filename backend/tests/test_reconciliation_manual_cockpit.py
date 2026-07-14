import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.reconciliation import ReconciliationResult
from app.models.transaction import Transaction


def _database_available():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_manual_match_unmatch_history_and_rollback():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Manual Recon Firm {suffix}"
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"recon-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}
        client = api.post("/clients", headers=headers, json={"name": "Recon Client", "entity_type": "pvt_ltd"})
        assert client.status_code == 201
        client_id = client.json()["id"]

        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            purchase = Transaction(
                org_id=org.id, client_id=client_id, source="upload", invoice_no="P-1",
                vendor_name="Apex Vendor", vendor_gstin="27ABCDE1234F1Z5", amount=1000, date=date(2026, 6, 1),
            )
            gstr2b = Transaction(
                org_id=org.id, client_id=client_id, source="gstr2b", invoice_no="P-1",
                vendor_name="Apex Vendor", vendor_gstin="27ABCDE1234F1Z5", amount=1000, date=date(2026, 6, 1),
            )
            result = ReconciliationResult(
                org_id=org.id, client_id=client_id, period="2026-06", status="completed",
                total_purchase=1000, total_gstr2b=1000, matched_count=0, unmatched_count=1, mismatch_value=1000,
            )
            db.add_all([purchase, gstr2b, result])
            db.commit()
            purchase_id = str(purchase.id)
            gstr2b_id = str(gstr2b.id)
            result_id = str(result.id)

        matched = api.post("/reconciliation/manual-match", headers=headers, json={
            "purchase_transaction_id": purchase_id,
            "gstr2b_transaction_id": gstr2b_id,
            "result_id": result_id,
            "reason": "Portal invoice verified manually",
            "confidence": 99,
        })
        assert matched.status_code == 200
        assert matched.json()["action_type"] == "manual_match"
        assert matched.json()["new_status"] == "tolerance"

        txns = api.get(f"/reconciliation/transactions?client_id={client_id}", headers=headers)
        assert txns.status_code == 200
        purchase_row = next(row for row in txns.json() if row["id"] == purchase_id)
        assert purchase_row["match_status"] == "tolerance"
        assert float(purchase_row["match_confidence"]) == 99

        actions = api.get(f"/reconciliation/actions?transaction_id={purchase_id}", headers=headers)
        assert actions.status_code == 200
        assert len(actions.json()) == 1

        unmatched = api.post("/reconciliation/unmatch", headers=headers, json={
            "purchase_transaction_id": purchase_id,
            "result_id": result_id,
            "reason": "Supporting GSTIN was later rejected",
        })
        assert unmatched.status_code == 200
        assert unmatched.json()["new_status"] == "unmatched"

        rollback = api.post(f"/reconciliation/actions/{matched.json()['id']}/rollback", headers=headers)
        assert rollback.status_code == 200
        assert rollback.json()["action_type"] == "rollback"
        assert rollback.json()["new_status"] == "unmatched"

        events = api.get("/events?event_type=reconciliation.manual_match", headers=headers)
        assert events.status_code == 200
        assert events.json()
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
