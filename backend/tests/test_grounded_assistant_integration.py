import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import SessionLocal
from app.main import app
from app.models.legal_chunk import LegalChunk
from app.models.organization import Organization


def _database_available():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _database_available(), reason="PostgreSQL is not available")
def test_ask_now_returns_grounded_answer_and_event():
    api = TestClient(app)
    suffix = uuid.uuid4().hex
    org_name = f"Grounded AI Firm {suffix}"
    try:
        registered = api.post("/auth/register", json={
            "org_name": org_name,
            "email": f"grounded-{suffix}@example.com",
            "password": "StrongPass123!",
        })
        assert registered.status_code == 201
        headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

        low = api.post("/clients", headers=headers, json={
            "name": "Low Health Source Client",
            "entity_type": "pvt_ltd",
        })
        assert low.status_code == 201
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            db.execute(
                text("UPDATE clients SET health_score = 42 WHERE id = :client_id"),
                {"client_id": low.json()["id"]},
            )
            db.add(LegalChunk(
                doc_type="income_tax_act",
                content="Section 142 notice response should be reviewed with supporting books of account and reconciliations.",
            ))
            db.commit()

        answer = api.post("/query/ask-now", headers=headers, json={
            "question": "Which clients have a health score below 50 and mention Section 142?"
        })
        assert answer.status_code == 200
        body = answer.json()
        assert body["row_count"] >= 1
        assert "Low Health Source Client" in body["answer"]
        assert body["confidence"] in {"low", "medium", "high"}
        assert body["grounding"]["capability"]["rag_mode"] in {"keyword_grounded", "semantic_vector"}
        assert body["grounding"]["source_count"] >= 1
        assert body["guardrails"]["tenant_scoped"] is True
        assert body["guardrails"]["read_only_sql"] is True

        events = api.get("/events?event_type=assistant.query.answered", headers=headers)
        assert events.status_code == 200
        assert events.json()
        assert events.json()[0]["payload"]["row_count"] >= 1
    finally:
        with SessionLocal() as db:
            org = db.query(Organization).filter(Organization.name == org_name).first()
            if org:
                db.delete(org)
                db.commit()
