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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import resend_mailer as mailer

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
    org_name = body.get("org_name") or "Nova & Partners LLP"
    token = _fake_jwt(DEMO_USER["sub"], DEMO_USER["org_id"], "partner", email)
    # Fire verification email
    await mailer.send_email(
        template="email_verification",
        to=email,
        props={
            "user_name": email.split("@")[0].title(),
            "verify_url": f"https://cacopilot.example.com/verify?token={token}",
            "workspace_name": org_name,
        },
    )
    return {"access_token": token, "refresh_token": token, "token_type": "bearer"}

@app.post("/api/auth/logout")
def logout():
    return {"ok": True}

@app.post("/api/auth/password-reset/request")
async def prr(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    if email:
        await mailer.send_email(
            template="password_reset",
            to=email,
            props={
                "user_name": email.split("@")[0].title(),
                "reset_url": f"https://cacopilot.example.com/reset-password?token=demo-{random.randint(100000,999999)}",
                "expires_in": "30 minutes",
            },
        )
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


@app.post("/api/users/invitations")
async def users_invite(request: Request):
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    role = (body.get("role") or "manager").title()
    inviter = (body.get("inviter_name") or "Priya · Partner")
    workspace = body.get("workspace_name") or "Nova & Partners LLP"
    if email:
        await mailer.send_email(
            template="user_invitation",
            to=email,
            props={
                "invitee_name": email.split("@")[0].title(),
                "inviter_name": inviter,
                "workspace_name": workspace,
                "role": role,
                "accept_url": f"https://cacopilot.example.com/register?invite=demo-{random.randint(100000,999999)}",
            },
        )
    return {"ok": True, "invited": email, "role": role}

@app.get("/api/users/me")
def me():
    return {**DEMO_USER, "id": DEMO_USER["sub"]}

# ---------------------------------------------------------------------------
# Emergent Google Auth — preview stub
# ---------------------------------------------------------------------------

@app.get("/api/auth/google/config")
def rz_google_config():
    return {
        "provider": "emergent_google_auth",
        "configured": True,
        "signup_mode": "auto_partner",   # preview: drop straight into dashboard
        "allowed_domains": [],
        "auth_url": "https://auth.emergentagent.com/",
        "preview_stub": True,
    }

@app.post("/api/auth/google/session")
async def rz_google_session(request: Request):
    """Preview stub — accepts ANY session_id and returns a demo JWT.

    Real backend (docker-compose) actually calls Emergent /session-data.
    """
    body = await request.json()
    sid = (body.get("session_id") or "").strip()
    if not sid:
        return JSONResponse({"detail": "session_id required"}, status_code=400)
    # In the preview stub, we don't actually contact Emergent auth service.
    # Simulate a Google sign-in for the demo user.
    email = f"google.demo.{sid[:6].lower()}@cacopilot.example.com"
    tok = _fake_jwt(DEMO_USER["sub"], DEMO_USER["org_id"], DEMO_USER["role"], email)
    return {
        "access_token": tok,
        "refresh_token": tok,
        "token_type": "bearer",
        "user": {
            "id": DEMO_USER["sub"],
            "org_id": DEMO_USER["org_id"],
            "email": email,
            "role": DEMO_USER["role"],
            "name": "Google Demo User",
            "picture": None,
        },
    }


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

# ---------------------------------------------------------------------------
# Razorpay — preview stub
# ---------------------------------------------------------------------------

PLANS = [
    {"code": "starter",    "name": "Starter",    "tagline": "Solo & small practice — up to 25 clients",
     "amount_inr": 2499,  "period": "monthly", "interval": 1,
     "features": ["GST reconciliation", "Deadlines & reminders", "Client portal (5 users)", "Basic AI review"]},
    {"code": "pro",        "name": "Pro",        "tagline": "Growing firm — up to 150 clients",
     "amount_inr": 5999,  "period": "monthly", "interval": 1,
     "features": ["Everything in Starter", "Exception Autopilot", "Notice drafter + certificates", "WhatsApp collections"]},
    {"code": "enterprise", "name": "Enterprise", "tagline": "Full command deck — unlimited clients",
     "amount_inr": 14999, "period": "monthly", "interval": 1,
     "features": ["Everything in Pro", "Benchmarking + RFP", "Audit papers + Ind AS 116", "SSO + priority support"]},
]

_STUB_SUBS: List[Dict[str, Any]] = []

@app.get("/api/razorpay/config")
def rz_config():
    return {
        "key_id": "rzp_test_STUB_PLACEHOLDER",
        "configured": False,   # explicitly false — placeholders only
        "webhook_configured": False,
        "currency": "INR",
        "test_mode": True,
        "preview_stub": True,
    }

@app.get("/api/razorpay/plans")
def rz_plans(): return PLANS

@app.post("/api/razorpay/orders")
async def rz_order(request: Request):
    body = await request.json()
    return {
        "order_id": f"order_STUB_{random.randint(10_000_000, 99_999_999)}",
        "amount_paise": int((body.get("amount_inr") or 0) * 100),
        "currency": "INR",
        "receipt": body.get("receipt"),
        "key_id": "rzp_test_STUB_PLACEHOLDER",
        "notes": {"stub": "true"},
    }

@app.post("/api/razorpay/verify-payment")
async def rz_verify(request: Request):
    # Preview stub — always verifies OK. Real backend uses HMAC-SHA256.
    return {"ok": True, "verified": True, "preview_stub": True}

@app.post("/api/razorpay/payment-links")
async def rz_link(request: Request):
    body = await request.json()
    lid = f"plink_STUB_{random.randint(10_000_000, 99_999_999)}"
    return {
        "id": lid,
        "short_url": f"https://rzp.io/l/{lid[-8:]}",
        "amount_inr": body.get("amount_inr"),
        "status": "created",
    }

@app.post("/api/razorpay/subscriptions")
async def rz_sub(request: Request):
    body = await request.json()
    plan = next((p for p in PLANS if p["code"] == body.get("plan_code")), PLANS[0])
    sub_id = f"sub_STUB_{random.randint(10_000_000, 99_999_999)}"
    row = {
        "id": f"sr-{len(_STUB_SUBS) + 1:04d}",
        "razorpay_subscription_id": sub_id,
        "plan_code": plan["code"],
        "amount_inr": plan["amount_inr"],
        "currency": "INR",
        "status": "created",
        "short_url": f"https://rzp.io/i/{sub_id[-8:]}",
        "next_charge_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _STUB_SUBS.append(row)

    # Fire subscription_activated email
    recipient = (body.get("email") or DEMO_USER["email"]).lower()
    await mailer.send_email(
        template="subscription_activated",
        to=recipient,
        props={
            "workspace_name": body.get("workspace_name") or "Nova & Partners LLP",
            "plan_name": plan["name"],
            "amount_inr": plan["amount_inr"],
            "next_charge_at": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%d %b %Y"),
            "dashboard_url": "https://cacopilot.example.com/dashboard",
        },
    )
    return row

@app.get("/api/razorpay/subscriptions")
def rz_sub_list(): return _STUB_SUBS

@app.delete("/api/razorpay/subscriptions/{sid}")
async def rz_sub_cancel(sid: str, request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    for r in _STUB_SUBS:
        if r["id"] == sid:
            r["status"] = "cancelled"
            plan = next((p for p in PLANS if p["code"] == r.get("plan_code")), PLANS[0])
            recipient = (body.get("email") or DEMO_USER["email"]).lower()
            await mailer.send_email(
                template="subscription_cancelled",
                to=recipient,
                props={
                    "workspace_name": body.get("workspace_name") or "Nova & Partners LLP",
                    "plan_name": plan["name"],
                    "ends_at": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%d %b %Y"),
                    "reactivate_url": "https://cacopilot.example.com/billing/reactivate",
                },
            )
            return {"ok": True, "id": sid, "status": "cancelled"}
    return {"ok": True, "id": sid, "status": "cancelled"}

# ---------------------------------------------------------------------------
# Resend — real integration (dry-run when RESEND_API_KEY=re_placeholder)
# ---------------------------------------------------------------------------

# Seed demo rows so the Email Signals panel isn't empty on first load
_CLIENTS_FOR_SEED = [{"name": c["name"], "email": c["email"]} for c in DEMO_CLIENTS[:14]]
mailer.seed_demo_log(_CLIENTS_FOR_SEED)


@app.get("/api/email/config")
def email_config():
    return {
        "provider": "resend",
        "dry_run": mailer.is_dry_run(),
        "from": mailer.from_address(),
        "webhook_configured": bool(
            mailer.RESEND_WEBHOOK_SECRET
            and not mailer.RESEND_WEBHOOK_SECRET.startswith("whsec_placeholder")
        ),
        "placeholder_key": mailer.is_placeholder(),
        "templates": [
            "password_reset", "email_verification", "user_invitation",
            "invoice_sent", "payment_received", "invoice_overdue",
            "subscription_activated", "subscription_cancelled", "subscription_halted",
            "document_request", "report_ready", "portal_invite",
        ],
        "bounced_count": len(mailer.BOUNCED_ADDRESSES),
    }


@app.get("/api/email/recent")
def email_recent():
    return sorted(mailer.EMAIL_LOG, key=lambda r: r.get("created_at") or "", reverse=True)[:100]


@app.get("/api/email/events")
def email_events():
    return mailer.EMAIL_EVENTS[:100]


@app.get("/api/email/bounced")
def email_bounced():
    return sorted(mailer.BOUNCED_ADDRESSES)


_SAMPLE_PROPS: Dict[str, Dict[str, Any]] = {
    "password_reset": {"user_name": "Priya", "reset_url": "https://cacopilot.example.com/reset?token=demo"},
    "email_verification": {"user_name": "Priya", "verify_url": "https://cacopilot.example.com/verify?token=demo"},
    "user_invitation": {"invitee_name": "Arjun", "inviter_name": "Priya · Partner", "role": "Manager",
                        "accept_url": "https://cacopilot.example.com/invite?token=demo"},
    "invoice_sent": {"client_name": "Aurora Textiles Pvt Ltd", "invoice_no": "INV-2026-1042",
                     "amount_inr": 148500, "due_date": "15 Aug 2026",
                     "view_url": "https://cacopilot.example.com/portal/invoices/inv-1042",
                     "pay_url": "https://rzp.io/l/inv-1042"},
    "payment_received": {"client_name": "Aurora Textiles Pvt Ltd", "invoice_no": "INV-2026-1042",
                         "amount_inr": 148500, "paid_at": "14 Jul 2026 · 16:42 IST",
                         "method": "Razorpay · UPI",
                         "receipt_url": "https://cacopilot.example.com/receipts/inv-1042.pdf"},
    "invoice_overdue": {"client_name": "Meridian Systems LLP", "invoice_no": "INV-2026-0921",
                        "amount_inr": 84200, "days_overdue": 12,
                        "pay_url": "https://rzp.io/l/inv-0921"},
    "subscription_activated": {"plan_name": "Pro", "amount_inr": 5999,
                               "next_charge_at": "14 Aug 2026",
                               "dashboard_url": "https://cacopilot.example.com/dashboard"},
    "subscription_cancelled": {"plan_name": "Pro", "ends_at": "31 Aug 2026",
                               "reactivate_url": "https://cacopilot.example.com/billing/reactivate"},
    "subscription_halted":    {"plan_name": "Pro", "reason": "card_declined",
                               "update_payment_url": "https://cacopilot.example.com/billing/payment-method"},
    "document_request": {"client_name": "Aurora Textiles Pvt Ltd", "ca_name": "Priya · Nova & Partners",
                         "document_list": ["Bank statement · SBI · Q1 FY26", "GSTR-2B · June 2026"],
                         "due_date": "20 Jul 2026",
                         "upload_url": "https://cacopilot.example.com/portal/upload/req-42"},
    "report_ready": {"client_name": "Aurora Textiles Pvt Ltd", "report_name": "GST Reconciliation",
                     "period": "Jun 2026",
                     "headline_metric": {"label": "Mismatched ITC", "value": "₹14,200", "tone": "warn"},
                     "view_url": "https://cacopilot.example.com/portal/reports/rec-jun26"},
    "portal_invite": {"contact_name": "Anil (Finance)", "ca_firm_name": "Nova & Partners LLP",
                      "portal_url": "https://cacopilot.example.com/portal/enter?token=demo"},
}


@app.post("/api/email/test-send")
async def email_test_send(request: Request):
    """Render + send (or dry-run) a template with sample or user-supplied props."""
    body = await request.json()
    template = (body.get("template") or "email_verification").strip()
    to = (body.get("to") or "demo@cacopilot.example.com").strip()
    props = body.get("props") or _SAMPLE_PROPS.get(template, {})
    subject_override = body.get("subject")

    entry = await mailer.send_email(
        template=template, to=to, props=props, subject_override=subject_override
    )
    return {
        "ok": entry.get("status") in {"sent", "delivered", "queued"},
        "id": entry["id"],
        "resend_message_id": entry.get("resend_message_id"),
        "status": entry["status"],
        "dry_run": entry["dry_run"],
        "template": template,
        "subject": entry["subject"],
        "error": entry.get("error"),
    }


@app.post("/api/email/webhook")
async def email_webhook(request: Request):
    """Resend/Svix webhook receiver — verifies signature, updates status, blacklists bounces."""
    raw = await request.body()
    try:
        payload = mailer.verify_and_parse_webhook(raw, dict(request.headers))
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=401)
    except Exception as exc:  # noqa
        return JSONResponse({"detail": f"parse error: {exc}"}, status_code=400)

    svix_id = request.headers.get("svix-id") or request.headers.get("Svix-Id")
    result = mailer.record_webhook_event(payload, svix_id=svix_id)
    return result


# ---------------------------------------------------------------------------
# Auto-fire real transactional flows on relevant existing endpoints
# ---------------------------------------------------------------------------


async def _fire(template: str, to: str, props: Dict[str, Any]) -> None:
    """Fire-and-forget helper — never crashes the caller."""
    try:
        await mailer.send_email(template=template, to=to, props=props)
    except Exception:  # noqa
        import logging
        logging.getLogger("ca_platform.email").exception("_fire failed for %s", template)

# ---------------------------------------------------------------------------
# Billing (used by the /billing page)
# ---------------------------------------------------------------------------

_STUB_INVOICES: List[Dict[str, Any]] = []

def _seed_invoices():
    if _STUB_INVOICES:
        return
    for i, c in enumerate(DEMO_CLIENTS[:12]):
        seed = random.Random(i * 7 + 1)
        total = seed.randint(15_000, 250_000)
        paid = 0 if i % 3 != 0 else int(total * 0.4)
        _STUB_INVOICES.append({
            "id": f"inv-{i:04d}",
            "client_id": c["id"],
            "client_name": c["name"],
            "invoice_no": f"INV-2026-{i + 1001}",
            "issue_date": (datetime.now(timezone.utc) - timedelta(days=seed.randint(3, 45))).date().isoformat(),
            "due_date":  (datetime.now(timezone.utc) + timedelta(days=seed.randint(-15, 20))).date().isoformat(),
            "total": total,
            "amount_paid": paid,
            "outstanding": total - paid,
            "days_overdue": max(seed.randint(-10, 20), 0),
            "status": "part_paid" if paid > 0 else seed.choice(["sent", "overdue", "draft"]),
            "payment_link": None,
        })

@app.get("/api/billing/overview")
def billing_overview():
    _seed_invoices()
    outstanding = sum(inv["outstanding"] for inv in _STUB_INVOICES)
    overdue = sum(inv["outstanding"] for inv in _STUB_INVOICES if inv["days_overdue"] > 0)
    collected = sum(inv["amount_paid"] for inv in _STUB_INVOICES)
    total = outstanding + collected
    return {
        "invoice_count": len(_STUB_INVOICES),
        "outstanding": outstanding,
        "overdue": overdue,
        "collected": collected,
        "collection_rate": int((collected / total) * 100) if total else 0,
        "active_plans": 6,
        "plans_due_next_30": 4,
        "by_status": {"sent": 5, "part_paid": 4, "overdue": 3},
        "ageing": {"0_30": outstanding * 0.5, "31_60": outstanding * 0.25, "61_90": outstanding * 0.15, "91_plus": outstanding * 0.1, "not_due": 0},
    }

@app.get("/api/billing/plan-usage")
def billing_plan_usage():
    return {
        "plan": "pro",
        "limits": {"clients": 150, "documents_per_month": 5000, "storage_gb": 100, "seats": 8, "whatsapp_msg": 4000},
        "usage":  {"clients": 24,  "documents_per_month": 1240, "storage_gb": 21,  "seats": 3, "whatsapp_msg": 640},
        "status": {"clients": "ok", "documents_per_month": "ok", "storage_gb": "ok", "seats": "ok", "whatsapp_msg": "ok"},
    }

@app.get("/api/billing/invoices")
def billing_invoices():
    _seed_invoices()
    return _STUB_INVOICES

@app.post("/api/billing/invoices")
async def billing_create_invoice(request: Request):
    _seed_invoices()
    body = await request.json()
    total = sum(li.get("amount", 0) for li in (body.get("line_items") or []))
    total = total * 1.18   # 18% GST
    inv = {
        "id": f"inv-new-{len(_STUB_INVOICES) + 1:04d}",
        "client_id": body.get("client_id"),
        "client_name": next((c["name"] for c in DEMO_CLIENTS if c["id"] == body.get("client_id")), "Client"),
        "invoice_no": f"INV-2026-{2000 + len(_STUB_INVOICES)}",
        "issue_date": body.get("issue_date"),
        "due_date": body.get("due_date"),
        "total": total, "amount_paid": 0, "outstanding": total, "days_overdue": 0,
        "status": body.get("status") or "sent",
        "payment_link": None,
    }
    _STUB_INVOICES.append(inv)

    # Fire invoice_sent email
    recipient = body.get("recipient_email") or next(
        (c["email"] for c in DEMO_CLIENTS if c["id"] == inv["client_id"]),
        "demo@cacopilot.example.com",
    )
    await mailer.send_email(
        template="invoice_sent",
        to=recipient,
        props={
            "client_name": inv["client_name"],
            "invoice_no": inv["invoice_no"],
            "amount_inr": int(inv["total"]),
            "due_date": inv["due_date"] or "30 days",
            "view_url": f"https://cacopilot.example.com/portal/invoices/{inv['id']}",
            "pay_url": f"https://rzp.io/l/{inv['id'][-8:]}",
        },
    )
    return inv

@app.patch("/api/billing/invoices/{iid}")
async def billing_patch(iid: str, request: Request):
    body = await request.json()
    for inv in _STUB_INVOICES:
        if inv["id"] == iid:
            inv.update(body)
            return inv
    return {"ok": True}

@app.post("/api/billing/invoices/{iid}/payments")
async def billing_pay(iid: str, request: Request):
    body = await request.json()
    for inv in _STUB_INVOICES:
        if inv["id"] == iid:
            amt = float(body.get("amount") or 0)
            inv["amount_paid"] += amt
            inv["outstanding"] = max(inv["total"] - inv["amount_paid"], 0)
            inv["status"] = "paid" if inv["outstanding"] == 0 else "part_paid"

            # Fire payment_received email
            recipient = body.get("recipient_email") or next(
                (c["email"] for c in DEMO_CLIENTS if c["id"] == inv.get("client_id")),
                "demo@cacopilot.example.com",
            )
            await mailer.send_email(
                template="payment_received",
                to=recipient,
                props={
                    "client_name": inv["client_name"],
                    "invoice_no": inv["invoice_no"],
                    "amount_inr": int(amt),
                    "paid_at": datetime.now(timezone.utc).strftime("%d %b %Y · %H:%M IST"),
                    "method": body.get("mode") or "Razorpay",
                    "receipt_url": f"https://cacopilot.example.com/receipts/{inv['id']}.pdf",
                },
            )
            return inv
    return {"ok": True}


@app.post("/api/billing/invoices/{iid}/remind")
async def billing_remind(iid: str, request: Request):
    """Send an invoice_overdue reminder email."""
    body = await request.json() if request.headers.get("content-length") else {}
    for inv in _STUB_INVOICES:
        if inv["id"] == iid:
            recipient = (body or {}).get("recipient_email") or next(
                (c["email"] for c in DEMO_CLIENTS if c["id"] == inv.get("client_id")),
                "demo@cacopilot.example.com",
            )
            entry = await mailer.send_email(
                template="invoice_overdue",
                to=recipient,
                props={
                    "client_name": inv["client_name"],
                    "invoice_no": inv["invoice_no"],
                    "amount_inr": int(inv["outstanding"] or inv["total"]),
                    "days_overdue": inv.get("days_overdue") or 1,
                    "pay_url": inv.get("payment_link") or f"https://rzp.io/l/{inv['id'][-8:]}",
                },
            )
            return {"ok": True, "email_id": entry["id"], "status": entry["status"]}
    return {"ok": False, "error": "invoice not found"}

@app.post("/api/billing/invoices/{iid}/payment-link")
def billing_link(iid: str):
    for inv in _STUB_INVOICES:
        if inv["id"] == iid:
            inv["payment_link"] = f"https://rzp.io/l/{iid[-8:]}"
            return {"invoice": inv}
    return {"ok": True}

@app.get("/api/billing/plans")
def billing_plans():
    return [
        {"id": f"pl-{i:03d}", "client_id": c["id"], "client_name": c["name"],
         "name": "Monthly retainer", "service_scope": ["GST", "TDS", "advisory"],
         "frequency": "monthly", "amount": 25000, "tax_rate": 18,
         "next_invoice_date": (datetime.now(timezone.utc) + timedelta(days=random.randint(1, 30))).date().isoformat(),
         "active": True}
        for i, c in enumerate(DEMO_CLIENTS[:8])
    ]

@app.post("/api/billing/plans")
async def billing_plan_create(request: Request):
    return {"ok": True}

@app.get("/api/billing/payments")
def billing_payments():
    _seed_invoices()
    return [{
        "id": f"pmt-{i:04d}",
        "invoice_no": inv["invoice_no"],
        "client_name": inv["client_name"],
        "paid_at": (datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))).date().isoformat(),
        "amount": inv["amount_paid"],
        "mode": random.choice(["razorpay", "bank_transfer", "upi"]),
        "reference": f"pay_{random.randint(10_000_000, 99_999_999)}",
    } for i, inv in enumerate(_STUB_INVOICES) if inv["amount_paid"] > 0]

@app.get("/api/portal/invoices")
def portal_invoices():
    _seed_invoices()
    # Client portal sees only their own open invoices — for preview return a few.
    return [inv for inv in _STUB_INVOICES if inv["outstanding"] > 0][:6]


# Portal actions that trigger emails
@app.post("/api/portal/document-requests")
async def portal_doc_request(request: Request):
    body = await request.json()
    recipient = (body.get("recipient_email") or "demo@cacopilot.example.com").lower()
    entry = await mailer.send_email(
        template="document_request",
        to=recipient,
        props={
            "client_name": body.get("client_name") or "Client",
            "ca_name": body.get("ca_name") or "Priya · Nova & Partners",
            "document_list": body.get("document_list") or ["Bank statement · Q1 FY26"],
            "due_date": body.get("due_date") or "in 7 days",
            "upload_url": body.get("upload_url") or "https://cacopilot.example.com/portal/upload",
        },
    )
    return {"ok": True, "email_id": entry["id"], "status": entry["status"]}


@app.post("/api/portal/reports/notify")
async def portal_report_ready(request: Request):
    body = await request.json()
    recipient = (body.get("recipient_email") or "demo@cacopilot.example.com").lower()
    entry = await mailer.send_email(
        template="report_ready",
        to=recipient,
        props={
            "client_name": body.get("client_name") or "Client",
            "report_name": body.get("report_name") or "Report",
            "period": body.get("period") or "This month",
            "headline_metric": body.get("headline_metric"),
            "view_url": body.get("view_url") or "https://cacopilot.example.com/portal/reports",
        },
    )
    return {"ok": True, "email_id": entry["id"], "status": entry["status"]}


@app.post("/api/portal/invite")
async def portal_invite(request: Request):
    body = await request.json()
    recipient = (body.get("recipient_email") or "").strip().lower()
    if not recipient:
        return JSONResponse({"detail": "recipient_email required"}, status_code=400)
    entry = await mailer.send_email(
        template="portal_invite",
        to=recipient,
        props={
            "contact_name": body.get("contact_name") or recipient.split("@")[0].title(),
            "ca_firm_name": body.get("ca_firm_name") or "Nova & Partners LLP",
            "portal_url": body.get("portal_url") or "https://cacopilot.example.com/portal/enter",
        },
    )
    return {"ok": True, "email_id": entry["id"], "status": entry["status"]}

# Catch-all: return empty list for any other /api GET so pages don't 404.
@app.get("/api/{full_path:path}")
def catchall(full_path: str):
    return JSONResponse([])

@app.post("/api/{full_path:path}")
async def catchall_post(full_path: str):
    return {"ok": True}
