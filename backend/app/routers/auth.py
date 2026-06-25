import hashlib
import base64
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.organization import Organization
from app.models.refresh_token import RefreshToken
from app.models.system import OrganizationAgentState, SystemAuditLog
from app.models.user import User
from app.schemas.auth import (
    EmailVerificationConfirmRequest, LoginRequest, LoginResponse, MfaDisableRequest,
    MfaSetupResponse, MfaVerifyRequest, PasswordResetConfirmRequest, PasswordResetRequest,
    RefreshRequest, RegisterRequest, TokenResponse,
)
from app.config import settings
from app.services.email_service import (
    EmailDeliveryError, assert_email_ready_for_production,
    send_email_verification_email, send_password_reset_email,
)
from app.utils.jwt_utils import create_access_token
from app.utils.events import publish_event

router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
MAX_ACTIVE_SESSIONS_PER_USER = 5

ROLE_PERMISSIONS = {
    "partner": [
        "org:manage",
        "team:manage",
        "client:write",
        "document:write",
        "reconciliation:run",
        "billing:manage",
        "audit:export",
        "assistant:ask",
    ],
    "manager": [
        "client:write",
        "document:write",
        "reconciliation:run",
        "audit:export",
        "assistant:ask",
    ],
    "article": [
        "client:read",
        "document:upload",
        "deadline:read",
        "assistant:ask",
    ],
}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _token_data(user: User) -> dict:
    return {
        "sub": str(user.id),
        "org_id": str(user.org_id),
        "role": user.role,
        "email": user.email,
        "perms": ROLE_PERMISSIONS.get(user.role, []),
    }


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _is_future(value: datetime | None) -> bool:
    if not value:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value > datetime.now(timezone.utc)


def _public_token_response(token: str, delivery: dict | None = None) -> dict:
    delivery = delivery or {}
    payload = {
        "detail": "If the email exists, a link will be sent.",
        "delivery_mode": delivery.get("mode") or ("development_response" if settings.ENV != "production" else "email_provider_pending"),
        "delivered": bool(delivery.get("delivered")),
    }
    if settings.ENV != "production" and not delivery.get("delivered"):
        payload["token"] = token
    return payload


def _totp_code(secret: str, timestep: int | None = None) -> str:
    counter = int(time.time() // 30) if timestep is None else timestep
    padded_secret = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded_secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{code % 1_000_000:06d}"


def _verify_totp(secret: str | None, code: str | None) -> bool:
    if not secret or not code:
        return False
    normalized = "".join(ch for ch in code if ch.isdigit())
    if len(normalized) != 6:
        return False
    current = int(time.time() // 30)
    return any(hmac.compare_digest(_totp_code(secret, current + drift), normalized) for drift in (-1, 0, 1))


def _new_mfa_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _new_recovery_codes() -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(8)]


def _hash_recovery_code(code: str) -> str:
    return _hash_token(code.strip().lower().replace(" ", ""))


def _load_recovery_hashes(user: User) -> list[str]:
    try:
        return json.loads(user.mfa_recovery_hashes or "[]")
    except json.JSONDecodeError:
        return []


def _consume_recovery_code(user: User, code: str | None) -> bool:
    if not code:
        return False
    hashes = _load_recovery_hashes(user)
    candidate = _hash_recovery_code(code)
    if candidate not in hashes:
        return False
    hashes.remove(candidate)
    user.mfa_recovery_hashes = json.dumps(hashes)
    return True


def _mfa_challenge(user: User) -> str:
    return _hash_token(f"{user.id}:{user.password_hash}:{user.mfa_confirmed_at}")


def _fingerprint(request: Request | None, device_hash: str | None = None) -> str:
    user_agent = request.headers.get("user-agent", "") if request else ""
    device = (device_hash or "").strip()
    return hashlib.sha256(f"{user_agent}|{device}".encode("utf-8")).hexdigest()


def _revoke_oldest_sessions(db: Session, user: User) -> None:
    active = db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False),
    ).order_by(RefreshToken.created_at.desc()).all()
    for session in active[MAX_ACTIVE_SESSIONS_PER_USER - 1:]:
        session.revoked = True
        session.revoked_at = datetime.now(timezone.utc)


def _risk_assessment(db: Session, user: User, request: Request | None, fingerprint_hash: str) -> tuple[str, list[str]]:
    ip = _client_ip(request)
    agent = request.headers.get("user-agent") if request else None
    reasons: list[str] = []
    previous = db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
    ).order_by(RefreshToken.created_at.desc()).limit(10).all()
    if previous and all(row.fingerprint_hash != fingerprint_hash for row in previous if row.fingerprint_hash):
        reasons.append("new_device")
    if ip and previous and all(row.ip_address != ip for row in previous if row.ip_address):
        reasons.append("new_ip")
    if agent and previous and all(row.user_agent != agent for row in previous if row.user_agent):
        reasons.append("new_user_agent")
    score = "high" if len(reasons) >= 2 else "medium" if reasons else "low"
    return score, reasons


def _store_refresh_token(db: Session, user: User, refresh_token: str, request: Request | None, device_hash: str | None,
                         hard_expires_at: datetime | None = None) -> None:
    now = datetime.now(timezone.utc)
    hard_expiry = hard_expires_at or now + timedelta(days=30)
    sliding_expiry = min(now + timedelta(days=7), hard_expiry)
    fingerprint_hash = _fingerprint(request, device_hash)
    risk_score, risk_reasons = _risk_assessment(db, user, request, fingerprint_hash)
    db.add(RefreshToken(
        org_id=user.org_id,
        user_id=user.id,
        token_hash=_hash_token(refresh_token),
        fingerprint_hash=fingerprint_hash,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent") if request else None,
        risk_score=risk_score,
        risk_reasons=json.dumps(risk_reasons),
        expires_at=sliding_expiry,
        hard_expires_at=hard_expiry,
    ))
    _revoke_oldest_sessions(db, user)


def _issue_tokens(db: Session, user: User, request: Request | None = None, device_hash: str | None = None,
                  hard_expires_at: datetime | None = None) -> TokenResponse:
    token_data = _token_data(user)
    token_data["fprint"] = _fingerprint(request, device_hash)
    refresh_token = secrets.token_urlsafe(64)
    _store_refresh_token(db, user, refresh_token, request, device_hash, hard_expires_at)
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=refresh_token,
    )


def _client_ip(request: Request | None) -> str | None:
    if not request:
        return None
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else None


def _seed_agent_state(db: Session, org: Organization) -> None:
    db.add(OrganizationAgentState(
        org_id=org.id,
        status="ready",
        vector_namespace=f"org_{org.id}",
        enabled_agents=[
            "autopilot",
            "notice_drafter",
            "nl_query",
            "benchmarking",
            "voice_agent",
        ],
        readiness_checks={
            "tenant_partition": True,
            "default_roles": ["partner", "manager", "article"],
            "vector_namespace": f"org_{org.id}",
            "event": "organization.initialized",
        },
    ))


def _write_system_audit(db: Session, request: Request, org: Organization, user: User, action: str, payload: dict) -> None:
    db.add(SystemAuditLog(
        org_id=org.id,
        actor_id=user.id,
        action=action,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        payload=payload,
    ))


def _record_failed_login(db: Session, user: User, request: Request) -> None:
    user.failed_login_count = int(user.failed_login_count or 0) + 1
    if user.failed_login_count >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCOUNT_LOCKOUT_MINUTES)
        _write_system_audit(db, request, user.organization, user, "AUTH_ACCOUNT_LOCKED", {
            "failed_login_count": user.failed_login_count,
            "locked_until": user.locked_until.isoformat(),
        })


def _clear_login_risk(user: User) -> None:
    user.failed_login_count = 0
    user.locked_until = None


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    email = _normalize_email(req.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if req.org_pan and db.query(Organization).filter(Organization.pan == req.org_pan).first():
        raise HTTPException(status_code=400, detail="Organization PAN already registered")
    org = Organization(name=req.org_name, pan=req.org_pan, gstin=req.gstin, firm_type=req.firm_type, status="active")
    db.add(org)
    db.flush()
    user = User(org_id=org.id, email=email, password_hash=pwd_ctx.hash(req.password), role="partner")
    db.add(user)
    db.flush()
    _seed_agent_state(db, org)
    _write_system_audit(db, request, org, user, "ORG_REGISTER", {
        "org_name": org.name,
        "org_pan_provided": bool(org.pan),
        "firm_type": org.firm_type,
        "actor_email": email,
        "event": "organization.initialized",
    })
    publish_event(
        db,
        org_id=org.id,
        actor_id=user.id,
        event_type="organization.initialized",
        aggregate_type="organization",
        aggregate_id=str(org.id),
        source_module="auth",
        payload={
            "org_name": org.name,
            "actor_email": email,
            "vector_namespace": f"org_{org.id}",
            "enabled_agents": ["autopilot", "notice_drafter", "nl_query", "benchmarking", "voice_agent"],
        },
    )
    tokens = _issue_tokens(db, user, request, None)
    db.commit()
    return tokens


@router.post("/login", response_model=LoginResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == _normalize_email(req.email)).first()
    if user and _is_future(user.locked_until):
        raise HTTPException(status_code=423, detail="Account temporarily locked")
    if not user or not pwd_ctx.verify(req.password, user.password_hash):
        if user:
            _record_failed_login(db, user, request)
            db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")
    _clear_login_risk(user)
    if user.mfa_enabled:
        challenge = _mfa_challenge(user)
        verified = _verify_totp(user.mfa_secret, req.mfa_code) or _consume_recovery_code(user, req.recovery_code)
        if not verified:
            db.commit()
            return LoginResponse(mfa_required=True, mfa_challenge=challenge)
    tokens = _issue_tokens(db, user, request, req.device_hash)
    db.commit()
    return LoginResponse(access_token=tokens.access_token, refresh_token=tokens.refresh_token)


@router.post("/password-reset/request")
def request_password_reset(payload: PasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    try:
        assert_email_ready_for_production()
    except EmailDeliveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    user = db.query(User).filter(User.email == _normalize_email(payload.email)).first()
    if user:
        token = secrets.token_urlsafe(48)
        user.password_reset_token_hash = _hash_token(token)
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)
        try:
            delivery = send_password_reset_email(user.email, token)
        except EmailDeliveryError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        _write_system_audit(db, request, user.organization, user, "AUTH_PASSWORD_RESET_REQUESTED", {
            "expires_at": user.password_reset_expires_at.isoformat(),
            "delivery_mode": delivery.get("mode"),
            "delivered": delivery.get("delivered"),
        })
        db.commit()
        return _public_token_response(token, delivery)
    return {"detail": "If the email exists, a reset link will be sent."}


@router.post("/password-reset/confirm")
def confirm_password_reset(payload: PasswordResetConfirmRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = _hash_token(payload.token)
    user = db.query(User).filter(User.password_reset_token_hash == token_hash).first()
    if not user or not _is_future(user.password_reset_expires_at):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.password_hash = pwd_ctx.hash(payload.new_password)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    _clear_login_risk(user)
    revoked_at = datetime.now(timezone.utc)
    user.tokens_revoked_at = revoked_at
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False),
    ).update({"revoked": True, "revoked_at": revoked_at}, synchronize_session=False)
    _write_system_audit(db, request, user.organization, user, "AUTH_PASSWORD_RESET_CONFIRMED", {
        "sessions_revoked": True,
    })
    db.commit()
    return {"detail": "Password reset complete"}


@router.post("/email-verification/request")
def request_email_verification(request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == request.state.user_id, User.org_id == request.state.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.email_verified_at:
        return {"detail": "Email is already verified"}
    token = secrets.token_urlsafe(48)
    user.email_verification_token_hash = _hash_token(token)
    user.email_verification_expires_at = datetime.now(timezone.utc) + timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
    try:
        delivery = send_email_verification_email(user.email, token)
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _write_system_audit(db, request, user.organization, user, "AUTH_EMAIL_VERIFICATION_REQUESTED", {
        "expires_at": user.email_verification_expires_at.isoformat(),
        "delivery_mode": delivery.get("mode"),
        "delivered": delivery.get("delivered"),
    })
    db.commit()
    return _public_token_response(token, delivery)


@router.post("/email-verification/confirm")
def confirm_email_verification(payload: EmailVerificationConfirmRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = _hash_token(payload.token)
    user = db.query(User).filter(User.email_verification_token_hash == token_hash).first()
    if not user or not _is_future(user.email_verification_expires_at):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    user.email_verified_at = datetime.now(timezone.utc)
    user.email_verification_token_hash = None
    user.email_verification_expires_at = None
    _write_system_audit(db, request, user.organization, user, "AUTH_EMAIL_VERIFIED", {})
    db.commit()
    return {"detail": "Email verified"}


@router.post("/refresh", response_model=TokenResponse)
def refresh(req: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    current_hash = _hash_token(req.refresh_token)
    session = db.query(RefreshToken).filter(
        RefreshToken.token_hash == current_hash,
    ).first()
    if not session:
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")
    user = db.query(User).filter(User.id == session.user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if session.revoked:
        session.replay_detected_at = datetime.now(timezone.utc)
        db.query(RefreshToken).filter(
            RefreshToken.user_id == session.user_id,
            RefreshToken.revoked.is_(False),
        ).update({"revoked": True, "revoked_at": datetime.now(timezone.utc)}, synchronize_session=False)
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token replay detected")
    if not session.is_active():
        raise HTTPException(status_code=401, detail="Refresh token revoked or expired")
    if session.fingerprint_hash and session.fingerprint_hash != _fingerprint(request, req.device_hash):
        session.revoked = True
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
        raise HTTPException(status_code=401, detail="Session fingerprint changed")

    tokens = _issue_tokens(db, user, request, req.device_hash, session.hard_expires_at)
    session.revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    session.replaced_by_hash = _hash_token(tokens.refresh_token)
    session.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return tokens


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = getattr(request.state, "user_id", None)
    org_id = getattr(request.state, "org_id", None)
    if not user_id or not org_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    revoked_at = datetime.now(timezone.utc)
    db.query(User).filter(User.id == user_id, User.org_id == org_id).update(
        {"tokens_revoked_at": revoked_at},
        synchronize_session=False,
    )
    db.query(RefreshToken).filter(
        RefreshToken.org_id == org_id,
        RefreshToken.user_id == user_id,
        RefreshToken.revoked.is_(False),
    ).update({"revoked": True, "revoked_at": revoked_at}, synchronize_session=False)
    db.commit()
    return {"detail": "Logged out"}


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == request.state.user_id, User.org_id == request.state.org_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    secret = _new_mfa_secret()
    recovery_codes = _new_recovery_codes()
    user.mfa_secret = secret
    user.mfa_enabled = False
    user.mfa_recovery_hashes = json.dumps([_hash_recovery_code(code) for code in recovery_codes])
    issuer = "CA Copilot"
    label = f"{issuer}:{user.email}"
    db.commit()
    return MfaSetupResponse(
        secret=secret,
        otpauth_url=f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&digits=6&period=30",
        recovery_codes=recovery_codes,
    )


@router.post("/mfa/enable")
def enable_mfa(payload: MfaVerifyRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == request.state.user_id, User.org_id == request.state.org_id).first()
    if not user or not _verify_totp(user.mfa_secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid MFA code")
    user.mfa_enabled = True
    user.mfa_confirmed_at = datetime.now(timezone.utc)
    db.commit()
    return {"detail": "MFA enabled", "mfa_enabled": True}


@router.post("/mfa/disable")
def disable_mfa(payload: MfaDisableRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == request.state.user_id, User.org_id == request.state.org_id).first()
    if not user or not pwd_ctx.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.mfa_enabled and not (_verify_totp(user.mfa_secret, payload.code) or _consume_recovery_code(user, payload.recovery_code)):
        raise HTTPException(status_code=400, detail="Valid MFA or recovery code required")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_hashes = None
    user.mfa_confirmed_at = None
    db.commit()
    return {"detail": "MFA disabled", "mfa_enabled": False}


@router.get("/sessions")
def list_sessions(request: Request, db: Session = Depends(get_db)):
    sessions = db.query(RefreshToken).filter(
        RefreshToken.org_id == request.state.org_id,
        RefreshToken.user_id == request.state.user_id,
    ).order_by(RefreshToken.created_at.desc()).limit(25).all()
    return [{
        "id": str(row.id),
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "risk_score": row.risk_score,
        "risk_reasons": json.loads(row.risk_reasons or "[]"),
        "revoked": row.revoked,
        "created_at": row.created_at,
        "last_used_at": row.last_used_at,
        "expires_at": row.expires_at,
    } for row in sessions]


@router.post("/sessions/{session_id}/revoke")
def revoke_session(session_id: str, request: Request, db: Session = Depends(get_db)):
    session = db.query(RefreshToken).filter(
        RefreshToken.id == session_id,
        RefreshToken.org_id == request.state.org_id,
        RefreshToken.user_id == request.state.user_id,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.revoked = True
    session.revoked_at = datetime.now(timezone.utc)
    db.commit()
    return {"detail": "Session revoked"}
