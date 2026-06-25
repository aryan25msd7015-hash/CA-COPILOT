import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.models.organization import Organization
from app.routers.auth import _totp_code


def _database_available():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_mfa_enrollment_login_recovery_and_session_controls():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"MFA Firm {suffix}"
    email = f"mfa-{suffix}@example.com"
    password = "StrongPass123!"
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": email,
            "password": password,
        })
        assert registered.status_code == 201
        access_token = registered.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        setup = api.post("/auth/mfa/setup", headers=headers)
        assert setup.status_code == 200
        setup_body = setup.json()
        assert setup_body["secret"]
        assert setup_body["otpauth_url"].startswith("otpauth://totp/")
        assert len(setup_body["recovery_codes"]) == 8

        enabled = api.post(
            "/auth/mfa/enable",
            headers=headers,
            json={"code": _totp_code(setup_body["secret"])},
        )
        assert enabled.status_code == 200
        assert enabled.json()["mfa_enabled"] is True

        challenged = api.post("/auth/login", json={"email": email, "password": password})
        assert challenged.status_code == 200
        assert challenged.json()["mfa_required"] is True
        assert challenged.json()["access_token"] is None

        bad_code = api.post("/auth/login", json={"email": email, "password": password, "mfa_code": "000000"})
        assert bad_code.status_code == 200
        assert bad_code.json()["mfa_required"] is True

        good_code = api.post(
            "/auth/login",
            headers={"user-agent": "MFA Test Browser/1"},
            json={"email": email, "password": password, "mfa_code": _totp_code(setup_body["secret"])},
        )
        assert good_code.status_code == 200
        assert good_code.json()["access_token"]
        mfa_headers = {"Authorization": f"Bearer {good_code.json()['access_token']}"}

        sessions = api.get("/auth/sessions", headers=mfa_headers)
        assert sessions.status_code == 200
        assert sessions.json()
        assert {"low", "medium", "high"}.issuperset({row["risk_score"] for row in sessions.json()})

        session_id = sessions.json()[0]["id"]
        revoked = api.post(f"/auth/sessions/{session_id}/revoke", headers=mfa_headers)
        assert revoked.status_code == 200

        recovery = api.post(
            "/auth/login",
            json={"email": email, "password": password, "recovery_code": setup_body["recovery_codes"][0]},
        )
        assert recovery.status_code == 200
        assert recovery.json()["access_token"]
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
