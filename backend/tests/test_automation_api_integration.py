import uuid
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.engines.automation_engines import get_fy, month_period
from app.main import app
from app.models.organization import Organization
from app.models.transaction import Transaction
from app.models.user import User


def _database_available():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def _assert_download(response):
    assert response.status_code == 200
    assert len(response.content) > 100


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_all_automation_module_api_workflows():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Automation Integration {suffix}"
    email = f"automation-{suffix}@example.com"
    headers = {}
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name, "email": email, "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        client = api.post("/clients", headers=headers, json={
            "name": "Integration Manufacturing Pvt Ltd",
            "entity_type": "pvt_ltd",
            "gstin": "27ABCDE1234F1Z5",
            "cin": "U28999MH2012PTC123456",
            "registered_office": "Mumbai",
        })
        assert client.status_code == 201
        client_id = client.json()["id"]

        calendar = api.get(f"/calendar/GSTR1/{month_period()}/clients", headers=headers)
        assert calendar.status_code == 200
        assert len(calendar.json()) == 1
        legacy_deadlines = api.get(f"/deadlines/client/{client_id}", headers=headers)
        assert legacy_deadlines.status_code == 200
        assert any(row["filing_type"] == "GSTR1" and row["period"] == month_period() for row in legacy_deadlines.json())
        assert api.patch(
            f"/calendar/items/{calendar.json()[0]['id']}",
            headers=headers, json={"data_received": True, "data_source": "integration_test"},
        ).status_code == 200

        vendor = api.post("/msme/vendors", headers=headers, json={
            "client_id": client_id,
            "certificate_text": (
                "Name of Enterprise: Integration Supplies\n"
                "UDYAM-MH-19-0123456\nSMALL ENTERPRISE\n27AAACR3333C1Z3"
            ),
        })
        assert vendor.status_code == 201
        with SessionLocal() as db:
            user = db.query(User).filter(User.email == email).first()
            db.add(Transaction(
                org_id=user.org_id, client_id=client_id, source="upload",
                invoice_no=f"MSME-{suffix[:8]}", vendor_name="Integration Supplies",
                vendor_gstin="27AAACR3333C1Z3", amount=125000,
                date=date.today() - timedelta(days=60), match_status="unmatched",
                fingerprint=f"integration-{suffix}",
            ))
            db.commit()
        assert api.post("/msme/scan", headers=headers, json={"client_id": client_id}).status_code == 200
        fy = get_fy(date.today() - timedelta(days=60))
        assert len(api.get(f"/msme/violations?client_id={client_id}&fy={fy}", headers=headers).json()) == 1
        _assert_download(api.get(f"/msme/export/{client_id}/{fy}", headers=headers))

        facility = api.post("/drawing-power/facilities", headers=headers, json={
            "client_id": client_id, "bank_name": "Integration Bank",
            "facility_type": "CC", "sanctioned_limit": 2000000,
            "margin_rules": {
                "stock_margin": .25, "debtor_margin": .25,
                "stock_age_cutoff_days": 180, "debtor_age_cutoff_days": 90,
                "creditor_deduction": True,
            },
        })
        assert facility.status_code == 201
        period = month_period()
        assert api.post("/drawing-power/ledger", headers=headers, json={
            "client_id": client_id, "period": period,
            "inventory": [{"sku": "STOCK-1", "stock_value": 1000000, "last_movement_date": str(date.today())}],
            "debtors": [{"debtor_name": "Customer", "invoice_date": str(date.today() - timedelta(days=30)), "outstanding": 500000, "payment_history_score": 90}],
        }).status_code == 200
        dp = api.post("/drawing-power/compute", headers=headers, json={
            "facility_id": facility.json()["id"], "period": period, "creditors": 100000,
        })
        assert dp.status_code == 200
        _assert_download(api.get(f"/drawing-power/export/{dp.json()['id']}.pdf", headers=headers))
        _assert_download(api.get(f"/drawing-power/export/{dp.json()['id']}.xlsx", headers=headers))

        cert_types = api.get("/certificates/types", headers=headers).json()
        assert len(cert_types) == 6
        for cert_type in cert_types:
            certificate = api.post("/certificates", headers=headers, json={
                "client_id": client_id, "cert_type": cert_type["id"],
                "fields": {field: 100 for field in cert_type["fields"]},
            })
            assert certificate.status_code == 201
            _assert_download(api.get(f"/certificates/{certificate.json()['id']}/export", headers=headers))

        for doc_type in ("board_minutes", "agm_notice", "mgt7", "aoc4"):
            secretarial = api.post("/secretarial", headers=headers, json={
                "client_id": client_id, "doc_type": doc_type,
                "transcript": "The directors approved the audited financial statements.",
                "data": {"meeting_date": str(date.today()), "chairman": "Integration Chair"},
            })
            assert secretarial.status_code == 201
            _assert_download(api.get(f"/secretarial/{secretarial.json()['id']}/export/docx", headers=headers))
            if doc_type == "board_minutes":
                _assert_download(api.get(f"/secretarial/{secretarial.json()['id']}/export/xml", headers=headers))

        lease = api.post("/leases", headers=headers, json={
            "client_id": client_id, "name": "Integration Lease",
            "source_text": "Lease term: 24 months. Monthly rent: INR 50000. IBR: 9%.",
            "data": {"lease_term_months": 24, "base_rent_monthly": 50000, "incremental_borrowing_rate_pct": 9},
        })
        assert lease.status_code == 201
        assert api.patch(f"/leases/{lease.json()['id']}", headers=headers, json={
            "data": {"base_rent_monthly": 52000}, "verified": True,
        }).status_code == 200
        _assert_download(api.get(f"/leases/{lease.json()['id']}/export", headers=headers))

        assert api.put("/rfp/credentials", headers=headers, json={
            "firm_name": "Integration CA Firm", "icai_regn_no": "FRN-999999W",
            "founding_year": 2000, "total_staff": 30,
            "gross_fee_receipts_fy1": 15000000, "gross_fee_receipts_fy2": 15000000,
            "gross_fee_receipts_fy3": 15000000, "peer_review_status": "valid",
        }).status_code == 200
        bid = api.post("/rfp/bids", headers=headers, json={
            "title": "Integration Audit RFP",
            "rfp_text": "At least 10 years, turnover INR 10000000, at least 20 staff, and valid peer review.",
        })
        assert bid.status_code == 201
        assert bid.json()["status"] == "generated"
        _assert_download(api.get(f"/rfp/bids/{bid.json()['id']}/export", headers=headers))

        entry = api.post("/timesheets/entries", headers=headers, json={
            "client_id": client_id, "date": str(date.today()), "hours_logged": 2,
            "task_description": "Integration review", "billable": True,
        })
        assert entry.status_code == 201
        assert api.post("/timesheets/activities", headers=headers, json={
            "client_id": client_id, "activity_type": "document_review", "duration_seconds": 7200,
        }).status_code == 201
        profitability = api.get(f"/timesheets/profitability?month={month_period()}", headers=headers)
        assert profitability.status_code == 200
        assert any(row["client_id"] == client_id for row in profitability.json())
        assert api.delete(f"/timesheets/entries/{entry.json()['id']}", headers=headers).status_code == 204
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
            db.commit()
