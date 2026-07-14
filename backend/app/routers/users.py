import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from app.config import settings
from app.database import get_db
from app.models.refresh_token import RefreshToken
from app.models.system import SystemAuditLog
from app.models.user import TeamInvitation, User
from app.schemas.user import TeamInvitationOut, TeamInviteAccept, TeamInviteCreate, UserCreate, UserUpdate, UserOut
from app.utils.deps import get_current_user, require_role
from app.utils.scoped_query import scoped
from typing import List

router = APIRouter()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
ROLES = {"partner", "manager", "article"}
ROLE_RANK = {"article": 1, "manager": 2, "partner": 3}


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _partner_count(db: Session, org_id) -> int:
    return scoped(db, User, org_id).filter(User.role == "partner").count()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _assert_role_assignable(actor: User, role: str) -> None:
    if role not in ROLES:
        raise HTTPException(400, "Invalid role")
    if ROLE_RANK[role] > ROLE_RANK[actor.role]:
        raise HTTPException(403, "Cannot assign a role higher than your own")


def _invite_url(token: str) -> str:
    return f"{settings.FRONTEND_URL}/register?invite_token={token}"


def _audit(db: Session, request: Request, actor: User, action: str, payload: dict) -> None:
    db.add(SystemAuditLog(
        org_id=actor.org_id,
        actor_id=actor.id,
        action=action,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        payload=payload,
    ))


def _revoke_user_sessions(db: Session, user: User) -> int:
    revoked_at = datetime.now(timezone.utc)
    user.tokens_revoked_at = revoked_at
    return db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id,
        RefreshToken.revoked.is_(False),
    ).update({"revoked": True, "revoked_at": revoked_at}, synchronize_session=False)


@router.get("", response_model=List[UserOut])
def list_users(request: Request, db: Session = Depends(get_db),
               _=Depends(require_role(["partner"]))):
    return scoped(db, User, request.state.org_id).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(req: UserCreate, request: Request, db: Session = Depends(get_db),
                actor=Depends(require_role(["partner"]))):
    _assert_role_assignable(actor, req.role)
    email = _normalize_email(req.email)
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already in use")
    user = User(org_id=request.state.org_id, email=email,
                password_hash=pwd_ctx.hash(req.password), role=req.role)
    db.add(user)
    _audit(db, request, actor, "TEAM_USER_CREATED", {"target_email": email, "role": req.role})
    db.commit()
    db.refresh(user)
    return user


@router.get("/invitations", response_model=List[TeamInvitationOut])
def list_invitations(request: Request, db: Session = Depends(get_db),
                     _=Depends(require_role(["partner"]))):
    return scoped(db, TeamInvitation, request.state.org_id).order_by(TeamInvitation.created_at.desc()).all()


@router.post("/invitations", response_model=TeamInvitationOut, status_code=201)
def invite_user(req: TeamInviteCreate, request: Request, db: Session = Depends(get_db),
                actor=Depends(require_role(["partner"]))):
    _assert_role_assignable(actor, req.role)
    email = _normalize_email(req.email)
    if scoped(db, User, request.state.org_id).filter(User.email == email, User.status != "offboarded").first():
        raise HTTPException(400, "This user is already mapped to this organization")
    pending = scoped(db, TeamInvitation, request.state.org_id).filter(
        TeamInvitation.email == email,
        TeamInvitation.status == "pending",
        TeamInvitation.expires_at > datetime.now(timezone.utc),
    ).first()
    if pending:
        raise HTTPException(400, "A pending invitation already exists for this email")
    token = secrets.token_urlsafe(48)
    invite = TeamInvitation(
        org_id=request.state.org_id,
        email=email,
        role=req.role,
        token_hash=_hash_token(token),
        invited_by_user_id=actor.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
    )
    db.add(invite)
    _audit(db, request, actor, "TEAM_INVITE_GENERATED", {"target_email": email, "role": req.role})
    db.commit()
    db.refresh(invite)
    out = TeamInvitationOut.model_validate(invite)
    out.invite_url = _invite_url(token)
    return out


@router.post("/invitations/accept", response_model=UserOut, status_code=201)
def accept_invitation(req: TeamInviteAccept, request: Request, db: Session = Depends(get_db)):
    invite = db.query(TeamInvitation).filter(TeamInvitation.token_hash == _hash_token(req.token)).first()
    now = datetime.now(timezone.utc)
    if not invite or invite.status != "pending":
        raise HTTPException(400, "Invitation is invalid or already used")
    expires_at = invite.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        invite.status = "expired"
        db.commit()
        raise HTTPException(400, "Invitation has expired")
    if db.query(User).filter(User.email == invite.email).first():
        raise HTTPException(400, "Email already in use")
    user = User(
        org_id=invite.org_id,
        email=invite.email,
        password_hash=pwd_ctx.hash(req.password),
        role=invite.role,
        status="active",
    )
    db.add(user)
    db.flush()
    invite.status = "accepted"
    invite.accepted_at = now
    db.add(SystemAuditLog(
        org_id=invite.org_id,
        actor_id=user.id,
        action="TEAM_INVITE_ACCEPTED",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        payload={"email": invite.email, "role": invite.role},
    ))
    db.commit()
    db.refresh(user)
    return user


@router.post("/invitations/{invite_id}/revoke", response_model=TeamInvitationOut)
def revoke_invitation(invite_id: str, request: Request, db: Session = Depends(get_db),
                      actor=Depends(require_role(["partner"]))):
    invite = scoped(db, TeamInvitation, request.state.org_id).filter(TeamInvitation.id == invite_id).first()
    if not invite:
        raise HTTPException(404, "Invitation not found")
    if invite.status != "pending":
        raise HTTPException(400, "Only pending invitations can be revoked")
    invite.status = "revoked"
    invite.revoked_at = datetime.now(timezone.utc)
    _audit(db, request, actor, "TEAM_INVITE_REVOKED", {"target_email": invite.email, "role": invite.role})
    db.commit()
    db.refresh(invite)
    return invite


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: str, req: UserUpdate, request: Request,
                db: Session = Depends(get_db), actor=Depends(require_role(["partner"]))):
    user = scoped(db, User, request.state.org_id).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if req.email:
        email = _normalize_email(req.email)
        existing = db.query(User).filter(User.email == email, User.id != user.id).first()
        if existing:
            raise HTTPException(400, "Email already in use")
        user.email = email
    if req.role:
        _assert_role_assignable(actor, req.role)
        if user.role == "partner" and req.role != "partner" and _partner_count(db, request.state.org_id) <= 1:
            raise HTTPException(400, "Cannot remove the last partner")
        if ROLE_RANK[user.role] > ROLE_RANK[actor.role]:
            raise HTTPException(403, "Cannot modify a user higher than your own role")
        user.role = req.role
        _revoke_user_sessions(db, user)
    if req.status:
        if req.status not in {"active", "suspended", "offboarded"}:
            raise HTTPException(400, "Invalid status")
        if user.role == "partner" and req.status != "active" and _partner_count(db, request.state.org_id) <= 1:
            raise HTTPException(400, "Cannot deactivate the last partner")
        user.status = req.status
        if req.status != "active":
            _revoke_user_sessions(db, user)
    _audit(db, request, actor, "TEAM_USER_UPDATED", {"target_email": user.email, "role": user.role, "status": user.status})
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: str, request: Request, db: Session = Depends(get_db),
                actor=Depends(require_role(["partner"]))):
    user = scoped(db, User, request.state.org_id).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "User not found")
    if user.role == "partner" and _partner_count(db, request.state.org_id) <= 1:
        raise HTTPException(400, "Cannot delete the last partner")
    _revoke_user_sessions(db, user)
    user.status = "offboarded"
    _audit(db, request, actor, "TEAM_USER_OFFBOARDED", {"target_email": user.email, "role": user.role})
    db.commit()
