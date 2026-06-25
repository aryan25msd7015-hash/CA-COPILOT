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


def test_security_headers_and_request_id_on_public_route():
    response = TestClient(app).get("/", headers={"X-Request-ID": "test-request-id"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-id"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert int(response.headers["X-RateLimit-Limit"]) >= 1


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_security_diagnostics_reports_runtime_controls():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Security Firm {suffix}"
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"security-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        diagnostics = api.get("/diagnostics/security", headers=headers)
        assert diagnostics.status_code == 200
        body = diagnostics.json()
        assert body["security_headers"]["x_content_type_options"] == "nosniff"
        assert body["auth"]["server_side_refresh_revocation"] is True
        assert body["auth"]["mfa_supported"] is True
        assert "active_keys" in body["rate_limiter"]
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
