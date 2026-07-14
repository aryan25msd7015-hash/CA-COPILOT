"""
Preview-only stub backend for the CA Copilot frontend.

Purpose: serve realistic mock data on port 8001 (via /api/*) so the futuristic
frontend renders end-to-end in the Emergent preview environment. The REAL
backend lives in /app/backend/app/ and needs Postgres/Redis/Celery/S3 — that
runs via `docker compose up` locally (see README.md).

Endpoints implemented: auth, clients, deadlines, autopilot, reconciliation,
anomalies, invoices, notices, health-scores, benchmarking, whatsapp,
diagnostics, integrations, tasks, users, documents. All return demo data.
"""
from __future__ import annotations

import base64
import json
import time
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="CA Copilot · Preview Stub", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _b64(o: Dict[str, Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()

def _fake_jwt(sub: str, org: str, role: str, email: str) -> str:
    header = _b64({"alg": "none", "typ": "JWT"})
    now = int(time.time())
    payload = _b64({
        "sub": sub, "org_id": org, "role": role, "email": email,
        "iat": now, "exp": now + 60 * 60 * 8,
    })
    return f"{header}.{payload}."

DEMO_USER = {
    "sub": "u-demo-001",
    "org_id": "org-demo-001",
    "role": "partner",
    "email": "demo@cacopilot.example.com",
}

INDUSTRIES = ["Manufacturing", "IT Services", "Retail", "Trading", "Healthcare", "Logistics", "Fintech", "Real Estate"]
ENTITY_TYPES = ["pvt_ltd", "public_ltd", "llp", "partnership", "proprietorship"]
FIRST = ["Aurora", "Meridian", "Nimbus", "Vertex", "Arcadia", "Zenith", "Kestrel", "Helix", "Orbit", "Cascade",
         "Falcon", "Solace", "Halcyon", "Prism", "Trellis", "Astral", "Nova", "Beacon", "Cypher", "Lumen"]
LAST = ["Textiles", "Systems", "Retail", "Logistics", "Pharma", "Steel", "Foods", "Motors", "Ventures", "Labs",
        "Networks", "Bio", "Robotics", "Traders", "Exports", "Chemicals", "Metals", "Capital"]

def _make_client(i: int) -> Dict[str, Any]:
    seed = random.Random(i * 17 + 3)
    name = f"{seed.choice(FIRST)} {seed.choice(LAST)}"
    score = seed.randint(30, 99)
    return {
        "id": f"cli-{i:05d}",
        "name": name,
        "entity_type": seed.choice(ENTITY_TYPES),
        "gstin": f"{seed.randint(10, 37):02d}AABCA{seed.randint(1000, 9999)}A1Z{seed.randint(0, 9)}",
        "pan": f"AABC{name[:1].upper()}{seed.randint(1000, 9999)}A",
        "tan": None,
        "cin": None,
        "email": f"contact@{name.lower().replace(' ', '')}.in",
        "whatsapp_number": f"+91-{seed.randint(700, 999)}0{seed.randint(10000, 99999)}",
        "industry": seed.choice(INDUSTRIES),
        "registered_office": "Mumbai, MH",
        "health_score": score,
        "created_at": (datetime.now(timezone.utc) - timedelta(days=seed.randint(30, 900))).isoformat(),
    }

DEMO_CLIENTS: List[Dict[str, Any]] = [_make_client(i) for i in range(24)]

# ---------------------------------------------------------------------------
# Root/health
# ---------------------------------------------------------------------------

@app.get("/")
@app.get("/api")
@app.get("/api/")
def root():
    return {"status": "ok", "service": "ca-copilot-preview-stub", "version": "0.1.0"}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

@app.post("/api/auth/login")
@app.post("/api/auth/token")
async def login(request: Request):
    body = await request.json()
    email = (body.get("email") or DEMO_USER["email"]).lower()
    token = _fake_jwt(DEMO_USER["sub"], DEMO_USER["org_id"], DEMO_USER["role"], email)
    return {
        "access_token": token,
        "refresh_token": token,
        "token_type": "bearer",
        "mfa_required": False,
        "user": {**DEMO_USER, "email": email, "id": DEMO_USER["sub"]},
    }

@app.post("/api/auth/register")
async def register(request: Request):
    body = await request.json()
    email = (body.get("email") or DEMO_USER["email"]).lower()
    token = _fake_jwt(DEMO_USER["sub"], DEMO_USER["org_id"], "partner", email)
    return {"access_token": token, "refresh_token": token, "token_type": "bearer"}

@app.post("/api/auth/logout")
def logout():
    return {"ok": True}

@app.post("/api/auth/password-reset/request")
async def prr(request: Request):
    return {"ok": True, "token": "demo-reset-token"}

@app.post("/api/auth/password-reset/confirm")
async def prc(request: Request):
    return {"ok": True}

@app.post("/api/auth/email-verification/confirm")
async def evc(request: Request):
    return {"ok": True}

@app.post("/api/users/invitations/accept")
async def acc(request: Request):
    return {"ok": True}

@app.get("/api/users/me")
def me():
    return {**DEMO_USER, "id": DEMO_USER["sub"]}

@app.get("/api/users")
def users_list():
    return [
        {"id": "u-01", "email": "priya.partner@firm.in", "role": "partner", "status": "active"},
        {"id": "u-02", "email": "arjun.manager@firm.in", "role": "manager", "status": "active"},
        {"id": "u-03", "email": "neha.article@firm.in", "role": "article", "status": "active"},
    ]

@app.get("/api/organizations/me")
@app.get("/api/organizations")
def orgs():
    return {"id": DEMO_USER["org_id"], "name": "Nova & Partners LLP", "plan": "enterprise"}

# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@app.get("/api/clients")
def clients_list():
    return DEMO_CLIENTS

@app.get("/api/clients/{cid}")
def client_get(cid: str):
    for c in DEMO_CLIENTS:
        if c["id"] == cid:
            return c
    return DEMO_CLIENTS[0]

@app.post("/api/clients")
async def client_create(request: Request):
    body = await request.json()
    new = _make_client(len(DEMO_CLIENTS) + 1)
    new.update({k: v for k, v in body.items() if v})
    DEMO_CLIENTS.append(new)
    return new

@app.get("/api/clients/workload/distribution")
@app.get("/api/practice-ops/workload-distribution")
def workload_distribution():
    return {
        "distribution_anomalies": {"is_imbalanced": True, "std_dev_units": 4.7, "overloaded_resource_count": 2},
        "client_workload_complexities": [
            {"client_id": c["id"], "client_name": c["name"], "complexity_index": random.randint(30, 95),
             "risk_band": random.choice(["low", "medium", "high"]),
             "open_tasks": random.randint(0, 8), "overdue_deadlines": random.randint(0, 3),
             "failed_documents": random.randint(0, 2),
             "routing_suggestion": {"suggested_email": "arjun.manager@firm.in", "reason": "Best load fit"}}
            for c in DEMO_CLIENTS[:10]
        ],
        "team_utilization_profiles": [
            {"user_id": "u-01", "email": "priya.partner@firm.in", "total_units": 78, "utilization_pct": 92, "status": "overloaded"},
            {"user_id": "u-02", "email": "arjun.manager@firm.in", "total_units": 54, "utilization_pct": 68, "status": "healthy"},
            {"user_id": "u-03", "email": "neha.article@firm.in", "total_units": 41, "utilization_pct": 52, "status": "under-utilised"},
        ],
    }

# ---------------------------------------------------------------------------
# Deadlines / Health / Documents / etc.
# ---------------------------------------------------------------------------

@app.get("/api/deadlines")
@app.get("/api/deadlines/upcoming")
def deadlines():
    today = datetime.now(timezone.utc).date()
    kinds = ["GSTR-1", "GSTR-3B", "TDS-24Q", "ITR", "ROC-AOC4", "ROC-MGT7", "PT", "PF"]
    out = []
    for i, c in enumerate(DEMO_CLIENTS[:12]):
        out.append({
            "id": f"dl-{i}",
            "client_id": c["id"],
            "client_name": c["name"],
            "kind": random.choice(kinds),
            "due_date": (today + timedelta(days=random.randint(-3, 21))).isoformat(),
            "status": random.choice(["pending", "in_review", "filed", "missed"]),
            "risk_score": random.randint(10, 95),
            "assigned_to": "arjun.manager@firm.in",
        })
    return out

@app.get("/api/health-scores")
@app.get("/api/health-scores/portfolio")
def health_scores():
    return [{"client_id": c["id"], "client_name": c["name"], "score": c["health_score"],
             "band": "green" if c["health_score"] >= 75 else ("amber" if c["health_score"] >= 50 else "red")}
            for c in DEMO_CLIENTS]

@app.get("/api/documents")
def documents():
    return [{
        "id": f"doc-{i:04d}",
        "client_id": c["id"],
        "client_name": c["name"],
        "kind": random.choice(["invoice", "purchase", "bank_statement", "gstr2b", "tally_export"]),
        "status": random.choice(["ocr_complete", "processing", "queued", "ocr_failed"]),
        "size_kb": random.randint(80, 3800),
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 240))).isoformat(),
    } for i, c in enumerate(DEMO_CLIENTS[:15])]

# ---------------------------------------------------------------------------
# Autopilot
# ---------------------------------------------------------------------------

@app.get("/api/autopilot/overview")
def autopilot_overview():
    return {
        "exposure_total": 3_450_000,
        "estimated_review_effort_hours": 14.5,
        "estimated_time_saved_hours": 42.0,
        "recent_syncs": [{"source": "Tally", "at": datetime.now(timezone.utc).isoformat(), "rows": 4210}],
        "queue": [
            {"id": f"ex-{i}", "kind": random.choice(["gst_variance", "msme_exposure", "deadline_risk", "invoice_anomaly", "profitability_leakage"]),
             "client_id": c["id"], "client_name": c["name"], "severity": random.choice(["high", "medium", "low"]),
             "exposure": random.randint(20_000, 800_000), "evidence_count": random.randint(1, 6),
             "created_at": (datetime.now(timezone.utc) - timedelta(hours=i)).isoformat(),
             "status": random.choice(["open", "in_review", "resolved"])}
            for i, c in enumerate(DEMO_CLIENTS[:14])
        ],
    }

@app.post("/api/autopilot/refresh")
def autopilot_refresh():
    return {"ok": True}

@app.post("/api/autopilot/tally/sync")
async def autopilot_sync(request: Request):
    return {"ok": True, "rows_imported": random.randint(1200, 4800)}

@app.patch("/api/autopilot/exceptions/{xid}")
async def autopilot_update(xid: str, request: Request):
    return {"ok": True, "id": xid}

@app.post("/api/autopilot/followups")
async def autopilot_followups(request: Request):
    return {"ok": True, "sent": True}

# ---------------------------------------------------------------------------
# Other listings — return sensible mock data
# ---------------------------------------------------------------------------

def _client_rows(kind: str, statuses: List[str], n: int = 12) -> List[Dict[str, Any]]:
    return [{
        "id": f"{kind}-{i:04d}",
        "client_id": c["id"],
        "client_name": c["name"],
        "status": random.choice(statuses),
        "amount": random.randint(5_000, 850_000),
        "created_at": (datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 400))).isoformat(),
    } for i, c in enumerate(DEMO_CLIENTS[:n])]

@app.get("/api/reconciliation")
@app.get("/api/reconciliation/summaries")
def recon(): return _client_rows("rec", ["exact", "tolerance", "fuzzy", "unmatched"], 16)

@app.get("/api/anomalies")
def anomalies(): return _client_rows("an", ["open", "confirmed", "false_positive", "cleared"], 14)

@app.get("/api/invoices")
@app.get("/api/invoices/scans")
def invoices(): return _client_rows("inv", ["processing", "processed", "review_required", "risk_high"], 18)

@app.get("/api/notices")
def notices(): return _client_rows("nt", ["draft", "ready_to_draft", "in_review", "filed"], 10)

@app.get("/api/audit-papers")
def audit(): return _client_rows("aud", ["draft", "in_review", "approved", "filed"], 10)

@app.get("/api/whatsapp")
@app.get("/api/whatsapp/reminders")
def whatsapp(): return _client_rows("wa", ["queued", "processed", "opted_in", "blocked_no_consent"], 14)

@app.get("/api/benchmarking")
@app.get("/api/benchmarking/summary")
def bench(): return _client_rows("bm", ["better_than_peers", "in_range", "worse_than_peers", "insufficient"], 12)

@app.get("/api/diagnostics")
@app.get("/api/diagnostics/readiness")
def diag():
    return {
        "checks": [
            {"name": "Database migrations", "status": "ok"},
            {"name": "S3 storage", "status": "ok"},
            {"name": "Redis / Celery", "status": "ok"},
            {"name": "Anthropic key", "status": "ok"},
            {"name": "OpenAI key", "status": "warning"},
            {"name": "WhatsApp channel", "status": "ok"},
            {"name": "Azure Document Intelligence", "status": "warning"},
        ],
        "score": 86,
    }

@app.get("/api/integrations")
def integrations():
    return [
        {"id": "tally",     "name": "Tally Connector",  "status": "connected"},
        {"id": "anthropic", "name": "Anthropic Claude", "status": "connected"},
        {"id": "openai",    "name": "OpenAI GPT",       "status": "connected"},
        {"id": "azure_doc", "name": "Azure Doc AI",     "status": "provider_missing"},
        {"id": "whatsapp",  "name": "Meta WhatsApp",    "status": "connected"},
        {"id": "s3",        "name": "AWS S3",           "status": "connected"},
    ]

@app.get("/api/tasks")
def tasks_list():
    return _client_rows("tsk", ["queued", "running", "completed", "failed"], 20)

@app.get("/api/query/saved")
@app.get("/api/query")
def query_saved(): return []

@app.get("/api/events")
def events(): return {"items": []}

# Catch-all: return empty list for any other /api GET so pages don't 404.
@app.get("/api/{full_path:path}")
def catchall(full_path: str):
    return JSONResponse([])

@app.post("/api/{full_path:path}")
async def catchall_post(full_path: str):
    return {"ok": True}
