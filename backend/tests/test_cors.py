from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


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
