from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.utils.deps import require_role
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
        },
    }
