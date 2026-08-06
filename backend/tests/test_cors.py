from fastapi.testclient import TestClient

from app.config import settings
from app.main import app, _cors_origins


def test_protected_route_cors_preflight_does_not_require_token():
    response = TestClient(app).options(
        "/clients",
        headers={
            "Origin": settings.FRONTEND_URL,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.FRONTEND_URL


def test_cors_origins_include_frontend_urls(monkeypatch):
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000")
    monkeypatch.setattr(
        settings,
        "FRONTEND_URLS",
        "https://partner.example.com,https://ca.example.com,http://localhost:3000",
    )
    origins = _cors_origins()
    assert origins[0] == "http://localhost:3000"
    assert "https://partner.example.com" in origins
    assert "https://ca.example.com" in origins
    assert origins.count("http://localhost:3000") == 1
