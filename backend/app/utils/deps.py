from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.utils.scoped_query import scoped
from typing import List


MFA_ENROLLMENT_PATHS = {
    "/auth/mfa/setup",
    "/auth/mfa/enable",
    "/auth/logout",
    "/auth/email-verification/request",
}


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = getattr(request.state, "user_id", None)
    org_id = getattr(request.state, "org_id", None)
    if not user_id or not org_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user = db.query(User).filter(User.id == user_id, User.org_id == org_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is not active")
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org and (org.security_policy or {}).get("require_mfa") and not user.mfa_enabled:
        if request.url.path not in MFA_ENROLLMENT_PATHS:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="MFA enrollment required by organization")
    now = datetime.now(timezone.utc)
    last_active = user.last_active_at
    if last_active and last_active.tzinfo is None:
        last_active = last_active.replace(tzinfo=timezone.utc)
    if last_active and last_active < now - timedelta(days=30):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session inactive for over 30 days")
    if not last_active or last_active < now - timedelta(minutes=5):
        user.last_active_at = now
        db.commit()
    return user


def require_role(allowed_roles: List[str]):
    def checker(user: User = Depends(get_current_user)):
        if user.role not in allowed_roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
        return user
    return checker
