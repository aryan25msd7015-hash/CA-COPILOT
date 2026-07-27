from fastapi import Request
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

from app.database import SessionLocal, reset_current_org, set_current_org
from app.models.practice_ops import ClientPortalContact
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
    "/client-portal/auth/magic-link",
    "/client-portal/auth/confirm",
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

    auth_context = payload.get("auth_context") or "firm"
    org_id = payload.get("org_id")
    if not org_id:
        return JSONResponse(status_code=401, content={"detail": "Token missing org_id"})

    if auth_context == "portal":
        # Client portal JWT — never resolve against firm users table.
        if payload.get("role") != "client":
            return JSONResponse(status_code=401, content={"detail": "Invalid portal token"})
        with SessionLocal() as db:
            contact = db.query(ClientPortalContact).filter(
                ClientPortalContact.id == payload.get("sub"),
                ClientPortalContact.org_id == org_id,
            ).first()
            if not contact:
                return JSONResponse(status_code=401, content={"detail": "Portal contact not found"})
            if contact.access_status in {"revoked", "disabled"}:
                return JSONResponse(status_code=403, content={"detail": "Portal access revoked"})
            if str(contact.client_id) != str(payload.get("client_id")):
                return JSONResponse(status_code=401, content={"detail": "Portal client mismatch"})
        request.state.org_id = org_id
        request.state.user_id = payload.get("sub")
        request.state.role = "client"
        request.state.auth_context = "portal"
        request.state.client_id = payload.get("client_id")
        # Firm APIs must reject portal tokens — only /client-portal/* is allowed.
        if not path.startswith("/client-portal"):
            return JSONResponse(status_code=403, content={"detail": "Portal token cannot access firm APIs"})
    else:
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == payload.get("sub"), User.org_id == org_id).first()
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
        request.state.org_id = org_id
        request.state.user_id = payload.get("sub")
        request.state.role = payload.get("role")
        request.state.auth_context = "firm"
        request.state.client_id = None
        # Firm users must not hit portal-only data APIs with firm JWT via confused deputy — allow admin paths only.
        if path.startswith("/client-portal/") and not path.startswith("/client-portal/auth/"):
            return JSONResponse(status_code=403, content={"detail": "Firm token cannot access client portal APIs"})

    context_token = set_current_org(request.state.org_id)
    try:
        return await call_next(request)
    finally:
        reset_current_org(context_token)
