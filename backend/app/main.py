"""FastAPI application entrypoint."""
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.middleware.tenant import tenant_middleware
from app.routers import (
    anomalies, audit_papers, auth, autopilot, benchmarking, clients, deadlines, documents, events,
    diagnostics, health_scores, integrations, invoices, notices, organizations, query, reconciliation,
    tasks, users, whatsapp, extensions, practice_ops,
)
from app.utils.security import client_ip, rate_limit_policy, rate_limiter

logger = logging.getLogger("ca_platform")

app = FastAPI(
    title="CA Intelligence Platform",
    version="1.0.0",
    description="Multi-tenant SaaS for Indian CA firms.",
)
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
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
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
]
for router, prefix, tag in ROUTERS:
    app.include_router(router, prefix=prefix, tags=[tag])


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "version": "1.0.0"}


@app.on_event("startup")
async def on_startup():
    logger.info("CA Intelligence Platform started")
