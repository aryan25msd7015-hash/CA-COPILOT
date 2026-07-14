"""FastAPI application entrypoint."""
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response

from app.config import settings
from app.middleware.tenant import tenant_middleware
from app.routers import (
    anomalies, audit_papers, auth, autopilot, benchmarking, clients, deadlines, documents, events,
    diagnostics, health_scores, integrations, invoices, notices, organizations, query, reconciliation,
    tasks, users, whatsapp, extensions, practice_ops, razorpay as razorpay_router,
    google_auth as google_auth_router,
)
from app.services.observability import configure_observability, record_request, render_metrics
from app.utils.security import client_ip, rate_limit_policy, rate_limiter

logger = logging.getLogger("ca_platform")
configure_observability()

app = FastAPI(
    title="CA Intelligence Platform",
    version="1.0.0",
    description="Multi-tenant SaaS for Indian CA firms.",
)
trusted_hosts = [host.strip() for host in settings.TRUSTED_HOSTS.split(",") if host.strip()]
if trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=trusted_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(tenant_middleware)


@app.middleware("http")
async def security_and_audit_middleware(request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    request.state.request_id = request_id
    policy = rate_limit_policy(request.url.path)
    if request.method != "OPTIONS" and policy:
        limit, window = policy
        key = f"{client_ip(request)}:{request.method}:{request.url.path}"
        allowed, remaining = rate_limiter.allow(key, limit=limit, window_seconds=window)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded", "request_id": request_id},
                headers={
                    "Retry-After": str(window),
                    "X-Request-ID": request_id,
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
    response = await call_next(request)
    duration_seconds = time.perf_counter() - started
    duration_ms = round(duration_seconds * 1000, 2)
    remaining = locals().get("remaining")
    limit = locals().get("limit")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Request-ID"] = request_id
    if limit is not None:
        response.headers["X-RateLimit-Limit"] = str(limit)
    if remaining is not None:
        response.headers["X-RateLimit-Remaining"] = str(remaining)
    if settings.ENV == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    record_request(request.method, request.url.path, response.status_code, duration_seconds)
    logger.info(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "org_id": getattr(request.state, "org_id", None),
        "user_id": getattr(request.state, "user_id", None),
        "method": request.method,
        "path": request.url.path,
        "status_code": response.status_code,
        "duration_ms": duration_ms,
        "client_ip": client_ip(request),
    }))
    return response


ROUTERS = [
    (auth.router, "/auth", "auth"),
    (autopilot.router, "/autopilot", "autopilot"),
    (organizations.router, "/organizations", "organizations"),
    (users.router, "/users", "users"),
    (clients.router, "/clients", "clients"),
    (documents.router, "/documents", "documents"),
    (events.router, "/events", "events"),
    (reconciliation.router, "/reconciliation", "reconciliation"),
    (deadlines.router, "/deadlines", "deadlines"),
    (whatsapp.router, "/whatsapp", "whatsapp"),
    (notices.router, "/notices", "notices"),
    (health_scores.router, "/health-scores", "health-scores"),
    (audit_papers.router, "/audit-papers", "audit-papers"),
    (anomalies.router, "/anomalies", "anomalies"),
    (invoices.router, "/invoices", "invoices"),
    (integrations.router, "/integrations", "integrations"),
    (diagnostics.router, "/diagnostics", "diagnostics"),
    (query.router, "/query", "query"),
    (benchmarking.router, "/benchmarking", "benchmarking"),
    (tasks.router, "/tasks", "tasks"),
    (extensions.router, "", "advanced-automation"),
    (practice_ops.router, "", "practice-operations"),
    (razorpay_router.router, "/razorpay", "razorpay"),
    (google_auth_router.router, "/auth/google", "google-auth"),
]
for router, prefix, tag in ROUTERS:
    app.include_router(router, prefix=prefix, tags=[tag])


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    if settings.ENV == "production" and settings.METRICS_BEARER_TOKEN:
        expected = f"Bearer {settings.METRICS_BEARER_TOKEN}"
        if request.headers.get("authorization") != expected:
            raise HTTPException(status_code=401, detail="Metrics token required")
    body, media_type = render_metrics()
    return Response(content=body, media_type=media_type)


@app.on_event("startup")
async def on_startup():
    logger.info("CA Intelligence Platform started")
