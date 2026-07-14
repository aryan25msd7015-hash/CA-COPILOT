from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from app.database import SessionLocal, reset_current_org, set_current_org
from app.models.user import User
from app.utils.jwt_utils import verify_token

# Paths that do not require a JWT
PUBLIC_PATHS = {
    "/",
    "/auth/register",
    "/auth/login",
    "/auth/refresh",
    "/auth/password-reset/request",
    "/auth/password-reset/confirm",
    "/auth/email-verification/confirm",
    "/billing/webhooks/razorpay",
    "/metrics",
    "/users/invitations/accept",
    "/docs",
    "/redoc",
    "/openapi.json",
}
PUBLIC_PREFIXES = ("/whatsapp/webhook", "/whatsapp/consent/", "/consent/", "/documents/local-upload/")


async def tenant_middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in PUBLIC_PATHS or any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Missing Bearer token"})
    token = auth_header.removeprefix("Bearer ").strip()
    try:
        payload = verify_token(token)
    except Exception:
        return JSONResponse(status_code=401, content={"detail": "Invalid or expired token"})
    if payload.get("type") != "access":
        return JSONResponse(status_code=401, content={"detail": "Access token required"})
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == payload.get("sub"), User.org_id == payload.get("org_id")).first()
        if not user:
            return JSONResponse(status_code=401, content={"detail": "User not found"})
        if user.status != "active":
            return JSONResponse(status_code=403, content={"detail": "User is not active"})
        revoked_at = user.tokens_revoked_at
        if revoked_at and revoked_at.tzinfo is None:
            revoked_at = revoked_at.replace(tzinfo=timezone.utc)
        issued_at = payload.get("iat")
        if revoked_at:
            if not issued_at:
                return JSONResponse(status_code=401, content={"detail": "Access token revoked"})
            issued_at_dt = datetime.fromtimestamp(issued_at, tz=timezone.utc)
            if issued_at_dt < revoked_at.replace(microsecond=0):
                return JSONResponse(status_code=401, content={"detail": "Access token revoked"})
    request.state.org_id = payload.get("org_id")
    request.state.user_id = payload.get("sub")
    request.state.role = payload.get("role")
    if not request.state.org_id:
        return JSONResponse(status_code=401, content={"detail": "Token missing org_id"})
    context_token = set_current_org(request.state.org_id)
    try:
        return await call_next(request)
    finally:
        reset_current_org(context_token)
