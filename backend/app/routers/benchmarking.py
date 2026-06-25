from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.models.organization import Organization
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped

router = APIRouter()


class ConsentRequest(BaseModel):
    client_id: str
    consent: bool = True
    source: str = Field(default="internal_approval", max_length=30)
    note: str | None = Field(default=None, max_length=1000)


def _consent_status(client: Client, org: Organization | None) -> dict:
    return {
        "client_id": str(client.id),
        "client_name": client.name,
        "industry": client.industry,
        "has_industry": bool(client.industry),
        "consent": bool(client.benchmark_consent_at),
        "consent_at": client.benchmark_consent_at.isoformat() if client.benchmark_consent_at else None,
        "consent_source": client.benchmark_consent_source,
        "consent_note": client.benchmark_consent_note,
        "consent_by_user_id": str(client.benchmark_consent_by_user_id) if client.benchmark_consent_by_user_id else None,
        "plan": org.plan if org else None,
        "premium_required": True,
        "can_compare": bool(org and org.plan == "premium" and client.industry),
        "can_contribute_to_pool": bool(client.benchmark_consent_at and client.industry),
    }


@router.get("/{client_id}")
def compare(client_id: str, request: Request, db: Session = Depends(get_db),
            _=Depends(require_role(["partner"]))):
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    if not org or org.plan != "premium":
        raise HTTPException(403, "Benchmarking requires the premium plan")
    client = scoped(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    if not client.industry:
        raise HTTPException(409, "Client industry is required for benchmarking")
    from app.engines.benchmarking_engine import compare_client

    return compare_client(client_id, db)


@router.get("/{client_id}/status")
def benchmark_status(client_id: str, request: Request, db: Session = Depends(get_db),
                     _=Depends(get_current_user)):
    client = scoped(db, Client, request.state.org_id).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    return _consent_status(client, org)


@router.post("/consent")
def consent(payload: ConsentRequest, request: Request, db: Session = Depends(get_db),
            user=Depends(require_role(["partner"]))):
    client = scoped(db, Client, request.state.org_id).filter(Client.id == payload.client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    if payload.consent and not client.industry:
        raise HTTPException(409, "Client industry is required before benchmarking consent")
    client.benchmark_consent_at = datetime.now(timezone.utc) if payload.consent else None
    client.benchmark_consent_source = payload.source.strip() if payload.consent else "revoked"
    client.benchmark_consent_note = payload.note.strip() if payload.note else None
    client.benchmark_consent_by_user_id = user.id
    db.commit()
    db.refresh(client)
    org = db.query(Organization).filter(Organization.id == request.state.org_id).first()
    return _consent_status(client, org)
