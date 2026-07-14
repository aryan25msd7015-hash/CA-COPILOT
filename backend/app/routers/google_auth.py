"""
Emergent-managed Google Auth router.

Adds "Sign in with Google" alongside the existing email/password + MFA flow.

Flow:
    Frontend  → redirects to https://auth.emergentagent.com/?redirect=<origin>/auth/callback
    Emergent  → returns to <origin>/auth/callback#session_id=<sid>
    Frontend  → POST /api/auth/google/session {session_id}
    Backend   → GET https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data
                with header X-Session-ID; receives {id, email, name, picture, session_token}
    Backend   → provisions/attaches the user per GOOGLE_SIGNUP_MODE + GOOGLE_ALLOWED_DOMAINS
    Backend   → issues the existing JWT (access + refresh) so the frontend `useAuth`
                and all authenticated routes just work.

REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
(the frontend derives redirect URL from window.location.origin).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.organization import Organization
from app.models.system import OrganizationAgentState, SystemAuditLog
from app.models.user import User
from app.routers.auth import _issue_tokens, _seed_agent_state  # reuse existing helpers

router = APIRouter()
log = logging.getLogger("ca_platform.google_auth")
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"


class GoogleSessionIn(BaseModel):
    session_id: str


class AwaitingApproval(BaseModel):
    detail: str
    email: EmailStr
    reason: str


def _domain_allowed(email: str) -> bool:
    allowlist = (getattr(settings, "GOOGLE_ALLOWED_DOMAINS", "") or "").strip()
    if not allowlist:
        return True
    domain = email.rsplit("@", 1)[-1].lower()
    allowed = {d.strip().lower() for d in allowlist.split(",") if d.strip()}
    return domain in allowed


def _signup_mode() -> str:
    mode = (getattr(settings, "GOOGLE_SIGNUP_MODE", "auto_pending") or "auto_pending").lower()
    return mode if mode in {"invited_only", "auto_pending", "auto_partner"} else "auto_pending"


async def _exchange_session(session_id: str) -> dict:
    """Call Emergent /session-data to trade session_id → user profile."""
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.get(EMERGENT_SESSION_URL, headers={"X-Session-ID": session_id})
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Emergent auth unreachable: {exc}") from exc
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session_id")
    try:
        data = r.json()
    except ValueError:
        raise HTTPException(status_code=502, detail="Emergent auth returned invalid JSON")
    if not data.get("email"):
        raise HTTPException(status_code=502, detail="Emergent auth payload missing email")
    return data


def _find_org_for_email(db: Session, email: str) -> Organization | None:
    """Prefer an existing pre-invited user's org, else the org matching the email domain."""
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing.organization
    domain = email.rsplit("@", 1)[-1].lower()
    return (
        db.query(Organization)
        .filter(Organization.domain_hint == domain)  # optional field; ignored if absent
        .first()
        if hasattr(Organization, "domain_hint") else None
    )


def _make_unusable_password() -> str:
    """Google-only users still need a password_hash column value; make it unusable."""
    return pwd_ctx.hash(secrets.token_urlsafe(48))


@router.get("/config")
def config():
    return {
        "provider": "emergent_google_auth",
        "configured": True,
        "signup_mode": _signup_mode(),
        "allowed_domains": [d.strip() for d in (settings.GOOGLE_ALLOWED_DOMAINS or "").split(",") if d.strip()],
        "auth_url": "https://auth.emergentagent.com/",
    }


@router.post("/session")
async def google_session(payload: GoogleSessionIn, request: Request, db: Session = Depends(get_db)):
    profile = await _exchange_session(payload.session_id)
    email = profile["email"].strip().lower()
    if not _domain_allowed(email):
        raise HTTPException(
            status_code=403,
            detail=f"Domain not allowed. Ask a partner to allowlist {email.rsplit('@', 1)[-1]}.",
        )

    mode = _signup_mode()
    existing = db.query(User).filter(User.email == email).first()

    if not existing:
        if mode == "invited_only":
            raise HTTPException(
                status_code=403,
                detail="Awaiting invite. A partner in this workspace must invite you before you can sign in.",
            )
        # Create a fresh org for the very first user; else attach to first org.
        org = _find_org_for_email(db, email) or db.query(Organization).order_by(Organization.created_at.asc()).first()
        founding = False
        if org is None:
            org = Organization(
                name=f"{profile.get('name') or email.split('@')[0]}'s workspace",
                firm_type="ca_firm",
                status="active",
            )
            db.add(org)
            db.flush()
            _seed_agent_state(db, org)
            founding = True

        role = "partner" if (mode == "auto_partner" or founding) else "article"
        user = User(
            org_id=org.id,
            email=email,
            password_hash=_make_unusable_password(),
            role=role,
            email_verified_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()

        db.add(SystemAuditLog(
            org_id=org.id,
            actor_id=user.id,
            action="AUTH_GOOGLE_SIGNUP",
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
            payload={"mode": mode, "founding": founding, "role": role, "picture": profile.get("picture")},
        ))
        # For auto_pending mode, return 202 so the frontend renders a
        # "we've queued you for approval" screen instead of dropping into the app.
        if mode == "auto_pending" and not founding:
            db.commit()
            raise HTTPException(
                status_code=202,
                detail=f"Signed up. Awaiting partner approval for {email}.",
            )
    else:
        user = existing
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise HTTPException(status_code=423, detail="Account temporarily locked")
        user.failed_login_count = 0
        user.locked_until = None
        db.add(SystemAuditLog(
            org_id=user.org_id,
            actor_id=user.id,
            action="AUTH_GOOGLE_LOGIN",
            ip_address=(request.client.host if request.client else None),
            user_agent=request.headers.get("user-agent"),
            payload={"picture": profile.get("picture")},
        ))

    tokens = _issue_tokens(db, user, request, device_hash=None)
    db.commit()
    return {
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "org_id": str(user.org_id),
            "email": user.email,
            "role": user.role,
            "name": profile.get("name"),
            "picture": profile.get("picture"),
        },
    }
