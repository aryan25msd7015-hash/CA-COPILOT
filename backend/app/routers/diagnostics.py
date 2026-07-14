from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.system import SystemAuditLog
from app.services.email_service import email_provider_status
from app.services.observability import observability_status
from app.services.payment_gateway import payment_gateway_status
from app.utils.deps import require_role
from app.utils.scoped_query import scoped
from app.utils.security import rate_limiter

router = APIRouter()


@router.get("/security")
def security_diagnostics(request: Request, _=Depends(require_role(["partner", "manager"]))):
    return {
        "organization_id": str(request.state.org_id),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "environment": settings.ENV,
        "security_headers": {
            "x_content_type_options": "nosniff",
            "x_frame_options": "DENY",
            "referrer_policy": "strict-origin-when-cross-origin",
            "hsts_enabled": settings.ENV == "production",
        },
        "rate_limiter": rate_limiter.snapshot(),
        "auth": {
            "access_token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            "refresh_token_expire_days": settings.REFRESH_TOKEN_EXPIRE_DAYS,
            "server_side_refresh_revocation": True,
            "mfa_supported": True,
            "password_reset_supported": True,
            "email_verification_supported": True,
            "max_failed_login_attempts": settings.MAX_FAILED_LOGIN_ATTEMPTS,
            "account_lockout_minutes": settings.ACCOUNT_LOCKOUT_MINUTES,
            "password_reset_token_expire_minutes": settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES,
            "email_verification_token_expire_hours": settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
        },
        "providers": {
            "email": email_provider_status(),
            "payments": payment_gateway_status(),
            "observability": observability_status(),
        },
    }


@router.get("/audit-log")
def audit_log(request: Request, limit: int = 50, db: Session = Depends(get_db), _=Depends(require_role(["partner", "manager"]))):
    limit = max(1, min(limit, 200))
    rows = scoped(db, SystemAuditLog, request.state.org_id).order_by(SystemAuditLog.created_at.desc()).limit(limit).all()
    return [{
        "id": str(row.id),
        "actor_id": str(row.actor_id) if row.actor_id else None,
        "action": row.action,
        "ip_address": row.ip_address,
        "user_agent": row.user_agent,
        "payload": row.payload or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    } for row in rows]
