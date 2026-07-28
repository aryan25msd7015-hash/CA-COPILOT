"""Client portal auth — separate JWT context from firm users.

Portal tokens use auth_context=portal, role=client, and sub=contact_id.
They must never be interchangeable with firm user JWTs.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.client import Client
from app.models.compliance_deadline import ComplianceDeadline
from app.models.document import Document
from app.models.practice_gaps import PortalAuthToken
from app.models.practice_ops import ClientPortalContact, PortalRequest, PracticeInvoice
from app.utils.jwt_utils import create_access_token
from app.utils.scoped_query import scoped

router = APIRouter()


class PortalMagicLinkRequest(BaseModel):
    email: EmailStr
    org_slug: str | None = None


class PortalMagicLinkConfirm(BaseModel):
    token: str = Field(min_length=20)


class PortalLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    contact: dict
    client: dict


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _contact_out(contact: ClientPortalContact, client: Client | None = None):
    return {
        "id": str(contact.id),
        "name": contact.name,
        "email": contact.email,
        "role": contact.role,
        "access_status": contact.access_status,
        "client_id": str(contact.client_id),
        "client_name": client.name if client else None,
        "org_id": str(contact.org_id),
    }


@router.post("/auth/magic-link")
def request_magic_link(payload: PortalMagicLinkRequest, db: Session = Depends(get_db)):
    """Issue a one-time magic link for an invited portal contact.

    Always returns a generic message to avoid email enumeration.
    In non-production, returns the raw token for local testing.
    """
    from app.config import settings

    email = payload.email.strip().lower()
    contact = (
        db.query(ClientPortalContact)
        .filter(ClientPortalContact.email == email)
        .order_by(ClientPortalContact.created_at.desc())
        .first()
    )
    response = {
        "detail": "If the contact exists and is invited, a portal link will be sent.",
        "delivery_mode": "development_response" if settings.ENV != "production" else "email_provider_pending",
    }
    if not contact or contact.access_status in {"revoked", "disabled"}:
        return response

    raw = secrets.token_urlsafe(32)
    row = PortalAuthToken(
        org_id=contact.org_id,
        client_id=contact.client_id,
        contact_id=contact.id,
        token_hash=_hash(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
    )
    db.add(row)
    db.commit()
    if settings.ENV != "production":
        response["token"] = raw
        response["expires_at"] = row.expires_at.isoformat()
    return response


@router.post("/auth/confirm", response_model=PortalLoginResponse)
def confirm_magic_link(payload: PortalMagicLinkConfirm, db: Session = Depends(get_db)):
    token_hash = _hash(payload.token.strip())
    row = db.query(PortalAuthToken).filter(PortalAuthToken.token_hash == token_hash).first()
    now = datetime.now(timezone.utc)
    if not row:
        raise HTTPException(401, "Invalid portal token")
    expires = row.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if row.consumed_at or expires < now:
        raise HTTPException(401, "Portal token expired or already used")

    contact = db.query(ClientPortalContact).filter(ClientPortalContact.id == row.contact_id).first()
    if not contact or contact.access_status in {"revoked", "disabled"}:
        raise HTTPException(403, "Portal access revoked")

    client = db.query(Client).filter(Client.id == contact.client_id, Client.org_id == contact.org_id).first()
    row.consumed_at = now
    contact.last_login_at = now
    contact.access_status = "active"
    db.commit()

    access = create_access_token({
        "sub": str(contact.id),
        "org_id": str(contact.org_id),
        "client_id": str(contact.client_id),
        "role": "client",
        "auth_context": "portal",
        "email": contact.email,
        "perms": [
            "portal:view_own",
            "portal:upload_docs",
            "portal:view_deadlines",
            "portal:view_invoices",
        ],
    })
    return PortalLoginResponse(
        access_token=access,
        contact=_contact_out(contact, client),
        client={
            "id": str(client.id) if client else str(contact.client_id),
            "name": client.name if client else "",
        },
    )


@router.post("/auth/demo-login", response_model=PortalLoginResponse)
def demo_portal_login(payload: PortalMagicLinkRequest, db: Session = Depends(get_db)):
    """Non-production helper: passwordless demo portal entry for seeded client contact."""
    from app.config import settings
    from app.utils.demo_credentials import DEMO_ACCOUNTS

    if settings.ENV == "production":
        raise HTTPException(403, "Demo portal login disabled in production")

    email = payload.email.strip().lower()
    demo = next((item for item in DEMO_ACCOUNTS if item["tier"] == "client" and item["email"] == email), None)
    if not demo:
        raise HTTPException(404, "Unknown demo client account")

    contact = (
        db.query(ClientPortalContact)
        .filter(ClientPortalContact.email == email)
        .order_by(ClientPortalContact.created_at.desc())
        .first()
    )
    if not contact:
        raise HTTPException(404, "Demo portal contact not seeded yet")

    client = db.query(Client).filter(Client.id == contact.client_id, Client.org_id == contact.org_id).first()
    contact.last_login_at = datetime.now(timezone.utc)
    contact.access_status = "active"
    db.commit()
    access = create_access_token({
        "sub": str(contact.id),
        "org_id": str(contact.org_id),
        "client_id": str(contact.client_id),
        "role": "client",
        "auth_context": "portal",
        "email": contact.email,
        "perms": [
            "portal:view_own",
            "portal:upload_docs",
            "portal:view_deadlines",
            "portal:view_invoices",
        ],
    })
    return PortalLoginResponse(
        access_token=access,
        contact=_contact_out(contact, client),
        client={
            "id": str(client.id) if client else str(contact.client_id),
            "name": client.name if client else "",
        },
    )


def _require_portal(request: Request):
    if getattr(request.state, "auth_context", None) != "portal":
        raise HTTPException(403, "Portal session required")
    if getattr(request.state, "role", None) != "client":
        raise HTTPException(403, "Client portal role required")
    return request


@router.get("/me")
def portal_me(request: Request, db: Session = Depends(get_db)):
    _require_portal(request)
    contact = db.query(ClientPortalContact).filter(
        ClientPortalContact.id == request.state.user_id,
        ClientPortalContact.org_id == request.state.org_id,
    ).first()
    if not contact:
        raise HTTPException(401, "Portal contact not found")
    client = scoped(db, Client, request.state.org_id).filter(Client.id == request.state.client_id).first()
    return {
        "auth_context": "portal",
        "tier": "client",
        "contact": _contact_out(contact, client),
        "features": [
            "client_portal",
            "document_vault_own",
            "compliance_calendar_own",
            "billing_own_invoices",
            "ask_ca_copilot_limited",
        ],
    }


@router.get("/deadlines")
def portal_deadlines(request: Request, db: Session = Depends(get_db)):
    _require_portal(request)
    rows = (
        scoped(db, ComplianceDeadline, request.state.org_id)
        .filter(ComplianceDeadline.client_id == request.state.client_id)
        .order_by(ComplianceDeadline.deadline.asc())
        .limit(100)
        .all()
    )
    return [{
        "id": str(r.id),
        "title": r.filing_name,
        "filing_type": r.filing_type,
        "period": r.period,
        "due_date": r.deadline.isoformat() if r.deadline else None,
        "status": r.status,
    } for r in rows]


@router.get("/documents")
def portal_documents(request: Request, db: Session = Depends(get_db)):
    _require_portal(request)
    rows = (
        scoped(db, Document, request.state.org_id)
        .filter(Document.client_id == request.state.client_id)
        .order_by(Document.created_at.desc())
        .limit(100)
        .all()
    )
    return [{
        "id": str(r.id),
        "filename": r.original_filename or "",
        "doc_type": r.doc_type,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]


@router.get("/invoices")
def portal_invoices(request: Request, db: Session = Depends(get_db)):
    _require_portal(request)
    rows = (
        scoped(db, PracticeInvoice, request.state.org_id)
        .filter(PracticeInvoice.client_id == request.state.client_id)
        .order_by(PracticeInvoice.issue_date.desc().nullslast())
        .limit(100)
        .all()
    )
    return [{
        "id": str(r.id),
        "invoice_no": r.invoice_no,
        "issue_date": r.issue_date.isoformat() if r.issue_date else None,
        "due_date": r.due_date.isoformat() if r.due_date else None,
        "total": float(r.total or 0),
        "amount_paid": float(r.amount_paid or 0),
        "outstanding": float(r.total or 0) - float(r.amount_paid or 0),
        "status": r.status,
        "payment_link": r.payment_link,
    } for r in rows]


@router.get("/requests")
def portal_requests(request: Request, db: Session = Depends(get_db)):
    _require_portal(request)
    rows = (
        scoped(db, PortalRequest, request.state.org_id)
        .filter(PortalRequest.client_id == request.state.client_id)
        .order_by(PortalRequest.created_at.desc())
        .limit(100)
        .all()
    )
    return [{
        "id": str(r.id),
        "title": r.title,
        "request_type": r.request_type,
        "status": r.status,
        "due_date": r.due_date.isoformat() if r.due_date else None,
        "description": r.description,
    } for r in rows]
