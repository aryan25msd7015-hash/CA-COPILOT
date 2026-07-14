# Technical Design Document — CA Intelligence Platform

## 1. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        CLIENT BROWSER                               │
│                    Next.js 14 Frontend (TypeScript)                 │
│           AG Grid · shadcn/ui · TanStack Query · React              │
└─────────────────────┬───────────────────────────────────────────────┘
                      │ HTTPS (REST + JSON)
┌─────────────────────▼───────────────────────────────────────────────┐
│                    FASTAPI BACKEND  (ap-south-1 ECS)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │  /auth   │ │ /clients │ │  /docs   │ │ /recon   │ │ /notices │ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │
│  │/whatsapp │ │/health   │ │/anomaly  │ │ /query   │ │/benchmark│ │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │
│              Tenant Middleware (JWT → org_id injection)             │
└───────┬─────────────────────────────────────┬───────────────────────┘
        │ Enqueue tasks                        │ DB queries (scoped)
┌───────▼────────────┐              ┌──────────▼──────────────────────┐
│   REDIS 7          │              │  POSTGRESQL 16  (RDS ap-south-1)│
│   (broker+backend) │              │  pgvector · uuid-ossp · pg_trgm │
└───────┬────────────┘              └─────────────────────────────────┘
        │
┌───────▼────────────────────────────────────────────────────────────┐
│                    CELERY WORKERS  (ECS Tasks)                     │
│  Queue: ocr     → Azure Document Intelligence OCR + PII Masking    │
│  Queue: heavy   → GST Reconciliation · Anomaly Detection           │
│  Queue: llm     → RAG Drafter · NL Query · Audit Papers            │
│  Queue: whatsapp→ Reminder Scheduler · Webhook Processing          │
│  Celery Beat    → Daily 09:00 IST compliance check                 │
└───┬────────────────┬──────────────────────┬────────────────────────┘
    │                │                      │
┌───▼───┐    ┌───────▼──────┐    ┌──────────▼───────┐
│ AWS   │    │ Azure Doc    │    │ Anthropic Claude  │
│  S3   │    │ Intelligence │    │ + OpenAI fallback │
│(docs) │    │   (OCR)      │    │   (LLM tasks)     │
└───────┘    └──────────────┘    └──────────────────┘
```

**Key architectural decisions:**
- Every DB table (except `organizations`, `legal_chunks`) carries `org_id` as a non-nullable FK.
- All write-heavy / long-running work is dispatched to Celery — FastAPI handlers stay under 200ms.
- AWS ap-south-1 for all storage and compute — DPDP Act 2023 compliance.
- Secrets live exclusively in AWS Secrets Manager, never in env files.

---

## 2. Technology Stack

| Layer | Choice | Version |
|---|---|---|
| Backend framework | FastAPI | 0.111+ |
| Language | Python | 3.11 |
| ORM | SQLAlchemy | 2.x |
| Migrations | Alembic | latest |
| Task queue | Celery | 5.x |
| Message broker | Redis | 7 |
| Database | PostgreSQL | 16 |
| DB extensions | pgvector, uuid-ossp, pg_trgm | — |
| Auth | python-jose (JWT) + passlib (bcrypt) | — |
| OCR | Azure Document Intelligence SDK | latest |
| LLM primary | Anthropic Claude (claude-sonnet-4) | — |
| LLM fallback | OpenAI GPT-4o | — |
| Embeddings | OpenAI text-embedding-3-small (1536-dim) | — |
| Fuzzy match | rapidfuzz | latest |
| ML anomaly | scikit-learn (IsolationForest) | latest |
| Data processing | pandas, numpy, scipy | latest |
| DOCX export | python-docx | latest |
| Excel export | openpyxl | latest |
| Cloud storage | AWS S3 (boto3) | latest |
| Secrets | AWS Secrets Manager | — |
| Frontend | Next.js 14 (App Router) | 14 |
| Frontend lang | TypeScript | 5 |
| Data tables | AG Grid Community | 31+ |
| UI components | shadcn/ui + Tailwind CSS | — |
| Data fetching | TanStack Query v5 | — |
| HTTP client | axios | — |
| Rich text | Tiptap | — |
| PDF viewer | react-pdf | — |
| Containerisation | Docker + Docker Compose | — |
| Production infra | AWS ECS Fargate | — |

---

## 3. Project Structure

```
ca-intelligence-platform/
├── backend/
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── app/
│   │   ├── main.py                  # FastAPI app factory
│   │   ├── config.py                # Settings from Secrets Manager
│   │   ├── database.py              # SQLAlchemy engine + session
│   │   ├── celery_app.py            # Celery instance + queue routing
│   │   ├── middleware/
│   │   │   └── tenant.py            # JWT → org_id injection
│   │   ├── models/                  # SQLAlchemy ORM models
│   │   │   ├── organization.py
│   │   │   ├── user.py
│   │   │   ├── client.py
│   │   │   ├── document.py
│   │   │   ├── transaction.py
│   │   │   ├── legal_chunk.py
│   │   │   ├── compliance_deadline.py
│   │   │   ├── whatsapp_reminder.py
│   │   │   ├── reconciliation.py
│   │   │   ├── health_history.py
│   │   │   ├── anomaly_flag.py
│   │   │   └── saved_query.py
│   │   ├── schemas/                 # Pydantic request/response models
│   │   │   ├── auth.py
│   │   │   ├── client.py
│   │   │   ├── document.py
│   │   │   ├── transaction.py
│   │   │   ├── reconciliation.py
│   │   │   ├── notice.py
│   │   │   ├── health.py
│   │   │   ├── query.py
│   │   │   └── benchmarking.py
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── organizations.py
│   │   │   ├── clients.py
│   │   │   ├── documents.py
│   │   │   ├── reconciliation.py
│   │   │   ├── deadlines.py
│   │   │   ├── whatsapp.py
│   │   │   ├── notices.py
│   │   │   ├── health_scores.py
│   │   │   ├── audit_papers.py
│   │   │   ├── anomalies.py
│   │   │   ├── invoices.py
│   │   │   ├── query.py
│   │   │   ├── benchmarking.py
│   │   │   └── tasks.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   ├── s3_service.py
│   │   │   ├── secrets_service.py
│   │   │   └── whatsapp_service.py
│   │   ├── tasks/
│   │   │   ├── ocr_tasks.py         # Queue: ocr
│   │   │   ├── reconciliation_tasks.py  # Queue: heavy
│   │   │   ├── anomaly_tasks.py     # Queue: heavy
│   │   │   ├── llm_tasks.py         # Queue: llm
│   │   │   └── whatsapp_tasks.py    # Queue: whatsapp
│   │   ├── engines/
│   │   │   ├── pii_masker.py
│   │   │   ├── tally_normalizer.py
│   │   │   ├── reconciliation_engine.py
│   │   │   ├── anomaly_detector.py
│   │   │   ├── deadline_engine.py
│   │   │   ├── rag_drafter.py
│   │   │   ├── health_score_engine.py
│   │   │   ├── invoice_fraud_scanner.py
│   │   │   ├── nl_query_engine.py
│   │   │   ├── audit_papers_engine.py
│   │   │   └── benchmarking_engine.py
│   │   └── utils/
│   │       ├── deps.py              # FastAPI dependency injectors
│   │       ├── jwt_utils.py
│   │       ├── scoped_query.py      # org_id-enforcing query helper
│   │       └── export_utils.py      # Excel / DOCX helpers
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│   ├── app/
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── register/page.tsx
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx           # Shell with sidebar + RBAC nav
│   │   │   ├── page.tsx             # Dashboard home (health scores)
│   │   │   ├── clients/
│   │   │   │   ├── page.tsx         # Client list + health badges
│   │   │   │   └── [id]/page.tsx    # Client detail
│   │   │   ├── documents/page.tsx
│   │   │   ├── reconciliation/
│   │   │   │   ├── page.tsx         # AG Grid transaction table
│   │   │   │   └── [id]/page.tsx
│   │   │   ├── deadlines/page.tsx   # Compliance calendar grid
│   │   │   ├── whatsapp/page.tsx    # WhatsApp status dashboard
│   │   │   ├── notices/page.tsx     # Notice RAG drafter
│   │   │   ├── audit/page.tsx       # Audit working papers
│   │   │   ├── anomalies/page.tsx   # Anomaly dashboard
│   │   │   ├── invoices/page.tsx    # Invoice fraud queue
│   │   │   ├── query/page.tsx       # NL query engine
│   │   │   └── benchmarking/page.tsx
│   │   └── layout.tsx
│   ├── components/
│   │   ├── ui/                      # shadcn/ui primitives
│   │   ├── layout/
│   │   │   ├── Sidebar.tsx
│   │   │   └── TopBar.tsx
│   │   ├── clients/
│   │   │   ├── ClientTable.tsx      # AG Grid
│   │   │   └── HealthBadge.tsx
│   │   ├── reconciliation/
│   │   │   └── ReconciliationGrid.tsx
│   │   ├── whatsapp/
│   │   │   └── WhatsAppStatusTable.tsx
│   │   └── shared/
│   │       ├── TaskStatusPoller.tsx
│   │       └── FileUploadZone.tsx
│   ├── hooks/
│   │   ├── useAuth.ts
│   │   ├── usePermission.ts         # RBAC hook
│   │   └── useTaskStatus.ts
│   ├── lib/
│   │   ├── api.ts                   # axios instance
│   │   └── auth.ts
│   ├── types/
│   │   └── index.ts
│   ├── next.config.ts
│   ├── tailwind.config.ts
│   └── package.json
│
├── docker-compose.yml               # Local dev: postgres, redis, backend, worker, frontend
├── docker-compose.prod.yml          # Prod: ECS-ready
└── README.md
```

---

## 4. Database Schema

```sql
-- Extensions (run once on fresh DB)
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ─────────────────────────────────────────
-- Core tenant tables
-- ─────────────────────────────────────────

CREATE TABLE organizations (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  name         TEXT NOT NULL,
  plan         TEXT NOT NULL DEFAULT 'starter',  -- starter | pro | premium
  gstin        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE users (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  email        TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role         TEXT NOT NULL CHECK (role IN ('partner','manager','article')),
  last_active_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_org ON users(org_id);

CREATE TABLE clients (
  id                    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id                UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  name                  TEXT NOT NULL,
  gstin                 TEXT,
  email                 TEXT,
  whatsapp_number       TEXT,
  whatsapp_consent_at   TIMESTAMPTZ,
  health_score          INT NOT NULL DEFAULT 100,
  industry              TEXT,
  benchmark_consent_at  TIMESTAMPTZ,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_clients_org ON clients(org_id);

-- ─────────────────────────────────────────
-- Documents & transactions
-- ─────────────────────────────────────────

CREATE TABLE documents (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id    UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  doc_type     TEXT NOT NULL CHECK (doc_type IN (
                 'invoice','gstr2b','purchase_register',
                 'notice','trial_balance','bank_statement')),
  s3_key       TEXT NOT NULL,
  ocr_text     TEXT,
  ocr_json     JSONB,
  source       TEXT NOT NULL DEFAULT 'upload' CHECK (source IN ('upload','whatsapp')),
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                 'pending','ocr_complete','ocr_failed',
                 'parse_failed','processed')),
  celery_task_id TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_documents_org      ON documents(org_id);
CREATE INDEX idx_documents_client   ON documents(client_id);
CREATE INDEX idx_documents_status   ON documents(status);

CREATE TABLE transactions (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id           UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id        UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  document_id      UUID REFERENCES documents(id) ON DELETE SET NULL,
  invoice_no       TEXT,
  vendor_gstin     TEXT,
  vendor_name      TEXT,
  amount           NUMERIC(15,2),
  tax_amount       NUMERIC(15,2),
  date             DATE,
  match_status     TEXT NOT NULL DEFAULT 'unmatched' CHECK (match_status IN (
                     'unmatched','exact','tolerance','fuzzy')),
  match_confidence NUMERIC(5,2),
  anomaly_score    NUMERIC(5,4),
  fraud_flag       TEXT,
  fingerprint      TEXT,
  source           TEXT NOT NULL DEFAULT 'upload',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_transactions_org       ON transactions(org_id);
CREATE INDEX idx_transactions_client    ON transactions(client_id);
CREATE INDEX idx_transactions_vendor    ON transactions(vendor_gstin);
CREATE INDEX idx_transactions_date      ON transactions(date);
CREATE INDEX idx_transactions_fingerprint ON transactions(fingerprint);

-- ─────────────────────────────────────────
-- Legal knowledge base (shared, no org_id)
-- ─────────────────────────────────────────

CREATE TABLE legal_chunks (
  id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  doc_type   TEXT NOT NULL CHECK (doc_type IN (
               'income_tax_act','gst_act','circular','reply_template')),
  content    TEXT NOT NULL,
  embedding  vector(1536),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_legal_chunks_embedding ON legal_chunks
  USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ─────────────────────────────────────────
-- Compliance & deadline tracking
-- ─────────────────────────────────────────

CREATE TABLE compliance_deadlines (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id    UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  filing_type  TEXT NOT NULL,  -- GSTR1, GSTR3B, TDS_24Q, TDS_26Q, ADVANCE_TAX, ROC
  filing_name  TEXT NOT NULL,
  period       TEXT NOT NULL,  -- e.g. "Oct-2024"
  deadline     DATE NOT NULL,
  status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                 'pending','filed','missed')),
  filed_at     TIMESTAMPTZ,
  doc_required TEXT,           -- document type required for this filing
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_deadlines_org    ON compliance_deadlines(org_id);
CREATE INDEX idx_deadlines_client ON compliance_deadlines(client_id);
CREATE INDEX idx_deadlines_date   ON compliance_deadlines(deadline);

CREATE TABLE whatsapp_reminders (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id    UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  deadline_id  UUID REFERENCES compliance_deadlines(id),
  template     TEXT NOT NULL,
  status       TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','failed')),
  sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_wa_reminders_client ON whatsapp_reminders(client_id);

-- ─────────────────────────────────────────
-- Reconciliation
-- ─────────────────────────────────────────

CREATE TABLE reconciliation_config (
  client_id        UUID PRIMARY KEY REFERENCES clients(id) ON DELETE CASCADE,
  amount_tolerance NUMERIC(10,2) NOT NULL DEFAULT 5,
  date_tolerance   INT NOT NULL DEFAULT 3,
  fuzzy_threshold  INT NOT NULL DEFAULT 85
);

CREATE TABLE reconciliation_results (
  id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id      UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  period         TEXT NOT NULL,
  total_purchase NUMERIC(15,2),
  total_gstr2b   NUMERIC(15,2),
  matched_count  INT,
  unmatched_count INT,
  mismatch_value NUMERIC(15,2),
  run_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_recon_results_client ON reconciliation_results(client_id);

-- ─────────────────────────────────────────
-- Health scores history
-- ─────────────────────────────────────────

CREATE TABLE client_health_history (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id    UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  score        INT NOT NULL,
  tier         TEXT NOT NULL CHECK (tier IN ('green','amber','red')),
  components   JSONB,
  computed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_health_history_client ON client_health_history(client_id);

-- ─────────────────────────────────────────
-- Anomaly flags
-- ─────────────────────────────────────────

CREATE TABLE anomaly_flags (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  client_id       UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  transaction_id  UUID REFERENCES transactions(id) ON DELETE CASCADE,
  flag_type       TEXT NOT NULL,  -- benford | round_number | weekend | duplicate | threshold_gaming | vendor_spike | isolation_forest
  risk_score      NUMERIC(5,4),
  details         JSONB,
  reviewed        BOOLEAN NOT NULL DEFAULT FALSE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_anomaly_flags_client ON anomaly_flags(client_id);

-- ─────────────────────────────────────────
-- Natural language saved queries
-- ─────────────────────────────────────────

CREATE TABLE saved_queries (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  org_id       UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  nl_query     TEXT NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_saved_queries_user ON saved_queries(user_id);
```

---

## 5. API Design

All endpoints (except `/auth/*`, `/whatsapp/webhook`, `/consent/*`) require `Authorization: Bearer <jwt>` header. The Tenant Middleware injects `org_id` and `role` from the JWT into `request.state` for every protected endpoint.

### Auth
```
POST   /auth/register          Create org + first partner user
POST   /auth/login             Returns access + refresh tokens
POST   /auth/refresh           Rotate refresh token
POST   /auth/logout
```

### Organizations
```
GET    /organizations/me       Own org details + plan
PATCH  /organizations/me       Update org info (partner only)
```

### Users
```
GET    /users                  List users in org (partner only)
POST   /users                  Create user (partner only)
PATCH  /users/{user_id}        Update role/email (partner only)
DELETE /users/{user_id}        (partner only)
```

### Clients
```
GET    /clients                List all clients (with health score)
POST   /clients                Create client
GET    /clients/{id}           Client detail
PATCH  /clients/{id}           Update client
DELETE /clients/{id}           (partner only)
GET    /clients/{id}/health-history
```

### Documents
```
POST   /documents/upload-url   Get S3 pre-signed URL + create Document record
GET    /documents              List documents (filterable by client, doc_type, status)
GET    /documents/{id}         Document detail + OCR result
POST   /documents/{id}/retry-ocr   Re-enqueue OCR task
```

### Reconciliation
```
POST   /reconciliation/run     Trigger reconciliation (async, returns task_id)
GET    /reconciliation/results/{client_id}  Latest reconciliation result
GET    /reconciliation/transactions         Paginated transaction list with filters
GET    /reconciliation/config/{client_id}
PUT    /reconciliation/config/{client_id}   Update tolerances
GET    /reconciliation/export/{result_id}   Download Excel report
```

### Compliance Deadlines
```
GET    /deadlines              Calendar view (all clients, upcoming deadlines)
POST   /deadlines              Create deadline
PATCH  /deadlines/{id}         Mark as filed
GET    /deadlines/client/{client_id}
```

### WhatsApp
```
GET    /whatsapp/consent/{token}     Client opt-in landing page (no auth)
POST   /whatsapp/webhook             Meta webhook (no auth, immediate 200)
POST   /whatsapp/send-manual         Send manual message (partner/manager)
GET    /whatsapp/status              All clients + document status + reminder log
POST   /whatsapp/unsubscribe/{client_id}  (partner only)
```

### Notices (RAG Drafter)
```
POST   /notices/draft          Submit notice doc_id → returns task_id
GET    /notices/draft/{task_id} Poll draft result
GET    /notices                List notices per client
```

### Health Scores
```
GET    /health-scores          All clients sorted by score
POST   /health-scores/recompute/{client_id}  Force recompute
```

### Audit Papers
```
POST   /audit-papers/generate  Submit trial_balance doc_id → returns task_id
GET    /audit-papers/{task_id} Poll result
GET    /audit-papers/export/{id}  Download DOCX
```

### Anomalies
```
GET    /anomalies              Anomaly dashboard for all clients
GET    /anomalies/client/{id}  Per-client anomaly flags
PATCH  /anomalies/{flag_id}/review  Mark as reviewed
```

### Invoice Fraud Scanner
```
GET    /invoices/fraud-queue   All fraud-flagged invoices
PATCH  /invoices/{id}/clear-flag  Clear fraud flag (partner only)
```

### Natural Language Query
```
POST   /query/ask              Submit NL query → returns result + SQL
GET    /query/saved            List saved queries
POST   /query/saved            Save a query
DELETE /query/saved/{id}
```

### Benchmarking
```
GET    /benchmarking/{client_id}   Compare client vs industry peers
POST   /benchmarking/consent       Opt-in org to data sharing
```

### Task Status
```
GET    /tasks/{celery_task_id}/status  Poll async task status
```

---

## 6. Core Module Designs

### 6.1 Multi-Tenant Middleware

```python
# app/middleware/tenant.py
async def tenant_middleware(request: Request, call_next):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    payload = verify_jwt(token)          # raises 401 if invalid/expired
    request.state.org_id = payload["org_id"]
    request.state.user_id = payload["sub"]
    request.state.role    = payload["role"]
    return await call_next(request)

# app/utils/scoped_query.py
def scoped(db: Session, Model, org_id: str):
    """Every DB query MUST go through this. Never query without org_id."""
    if not hasattr(Model, 'org_id'):
        raise RuntimeError(f"{Model.__name__} has no org_id — use direct query")
    return db.query(Model).filter(Model.org_id == org_id)
```

### 6.2 OCR Pipeline (Celery chain)

```
Document uploaded → S3
  ↓
[ocr queue] run_ocr(document_id)
  → Azure Document Intelligence prebuilt-invoice
  → extract_tables(), extract_key_values()
  → mask_pii(raw_text)
  → doc.ocr_text = masked_text
  → doc.ocr_json = {tables, kvs}
  → doc.status = "ocr_complete"
  ↓
route_doc(document_id)
  → if doc_type == 'invoice'         → extract_invoice_transactions.delay()
  → if doc_type == 'purchase_register' → extract_csv_transactions.delay()
  → if doc_type == 'gstr2b'          → extract_gstr2b.delay()
  → if doc_type == 'notice'          → (ready for RAG drafter, no auto-extract)
  → if doc_type == 'trial_balance'   → (ready for audit papers)
  → if doc_type == 'bank_statement'  → extract_bank_transactions.delay()
```

### 6.3 Reconciliation Engine (3-tier waterfall)

```
Input: purchase_df, gstr2b_df, config{amount_tol, date_tol, fuzz_thr}

Pre-pass: normalize both DataFrames
  - invoice_no → uppercase, strip non-alphanumeric except /,-
  - vendor_name → uppercase, strip PVT/LTD/PRIVATE/LIMITED/LLP
  - date → parse dayfirst=True
  - amount → round(2)

Tier 1 — Exact (confidence 100):
  Match on: vendor_gstin == vendor_gstin
          AND invoice_no == invoice_no
          AND amount == amount

Tier 2 — Tolerance (confidence 90):
  Remaining records only.
  Match on: vendor_gstin == vendor_gstin
          AND abs(amount_diff) <= amount_tol
          AND abs(date_diff_days) <= date_tol

Tier 3 — Fuzzy (confidence = fuzz_score):
  Remaining records only.
  Match on: fuzz.token_sort_ratio(vendor_name_p, vendor_name_g) >= fuzz_thr
          AND abs(amount_diff) <= amount_tol

Output: matched_df (with match_type, confidence), unmatched_df
```

### 6.4 WhatsApp Pipeline

```
Consent flow:
  CA → POST /clients/{id} with whatsapp_number
  System generates signed consent token (HMAC-SHA256, 24h TTL)
  CA shares URL: https://app.domain/consent/{token}
  Client opens URL → GET /whatsapp/consent/{token}
  System sets clients.whatsapp_consent_at = NOW()

Daily scheduler (Celery Beat, 09:00 IST):
  morning_reminder_check():
    deadlines = get_deadlines_within(days=10)
    for each deadline:
      skip if no consent
      skip if doc already received
      skip if reminder_count >= 3
      skip if reminder sent today
      days_left = deadline - today
      template = "filing_deadline_urgent" if days_left <= 1
               else "data_request_reminder"
      send_whatsapp_template.delay(number, template, params)
      log reminder to whatsapp_reminders

Webhook (POST /whatsapp/webhook):
  Return {"status":"ok"} immediately (< 200ms)
  BackgroundTask → process_incoming_wa(payload)
    if message.type == 'document':
      download_media → upload S3 → create Document → run_ocr.delay()
      send acknowledgment template
    if message.body == 'STOP':
      set client.whatsapp_consent_at = NULL
```

### 6.5 RAG Notice Drafter

```
Input: document_id (notice doc)

1. retrieve_legal_context(notice_ocr_text, k=5)
   → embed notice text with text-embedding-3-small
   → pgvector cosine similarity search on legal_chunks
   → return top-5 chunks

2. parse_notice(ocr_text)
   → extract: notice_type, section, AY, demand_amount, due_date

3. Claude generation (claude-sonnet-4):
   system: "Only cite sections present in CONTEXT. No invented case laws."
   context: joined top-5 chunks
   user: notice_data + "Draft formal reply"

4. validate_citations(draft, context)
   → regex extract all "Section X" references from draft
   → check each exists verbatim in context
   → flag unverified citations

5. Return: {draft, validation, source_chunks, notice_data}
```

### 6.6 Health Score Engine (0–100)

```
Component weights (total = 100):
  gst_score     = on_time_filings_last_12 / 12 * 25
  itc_score     = max(0, 25 * (1 - min(itc_gap_pct * 5, 1)))
  notice_score  = max(0, 25 - open_notices * 8)
  anomaly_score = max(0, 15 * (1 - min(anomaly_rate * 10, 1)))
  tds_score     = tds_on_time_rate * 10

total = round(sum of all components)
tier  = "green" if total >= 75
      | "amber" if total >= 50
      | "red"   otherwise

Nightly recompute: Celery Beat, 02:00 IST
  → recompute_all_health_scores()
  → update clients.health_score
  → insert into client_health_history
```

### 6.7 Anomaly Detector

```
After each reconciliation run:
  1. Isolation Forest (per client, last 6 months):
     features per vendor: [mean_amount, std_amount, txn_count]
     contamination=0.02
     score per transaction = normalized decision_function output (0–1)

  2. Benford's Law:
     first_digits = [int(str(abs(a))[0]) for a in amounts]
     chi-square test against BENFORD = [0.301, 0.176, ...]
     flag if p_value < 0.05

  3. Rule flags:
     round_number:  amount % 1000 == 0 AND amount > 10000
     weekend:       date.weekday() >= 5
     duplicate:     same (vendor_gstin, invoice_no, amount) in 30 days
     threshold_gaming: 45000 <= amount < 50000
     vendor_spike:  current_3m_total > prev_monthly_avg * 3

  4. Insert into anomaly_flags table
  5. Update transactions.anomaly_score
```

### 6.8 NL Query Engine

```
SCHEMA_CONTEXT = """
  clients(id, name, gstin, health_score, industry)
  transactions(id, client_id, invoice_no, vendor_name, vendor_gstin,
    amount, date, match_status, anomaly_score)
  compliance_deadlines(client_id, filing_type, period, deadline, status)
  client_health_history(client_id, score, tier, computed_at)
  documents(client_id, doc_type, source, status, created_at)
"""

Claude prompt:
  "Convert to PostgreSQL SELECT. Always include WHERE org_id = '{org_id}'.
   Return only SQL. No markdown. Block all write operations."

Safety layer:
  if any([kw in sql.upper() for kw in
          ['DELETE','UPDATE','INSERT','DROP','TRUNCATE','ALTER']]):
      raise ValueError("Write operations blocked")

Execute with SQLAlchemy text() parameterized by org_id.
Return: {sql, rows, row_count}
```

---

## 7. Security Design

### Secrets Management
```python
# app/services/secrets_service.py
import boto3, json

def get_secret(name: str) -> dict:
    client = boto3.client("secretsmanager", region_name="ap-south-1")
    return json.loads(
        client.get_secret_value(SecretId=name)["SecretString"])
```
All credentials loaded at startup from Secrets Manager. No `.env` files in production.

### Row-Level Security
PostgreSQL RLS policies enforce org_id at the DB engine level:
```sql
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
CREATE POLICY clients_isolation ON clients
  USING (org_id = current_setting('app.current_org_id')::uuid);
-- Repeated for all multi-tenant tables
```
The FastAPI app sets `SET LOCAL app.current_org_id = '{org_id}'` at the start of each transaction.

### PII Masking Pipeline
```
Rule 1: PAN    [A-Z]{5}[0-9]{4}[A-Z]        → [MASKED-{sha256[:8]}]
Rule 2: Aadhaar \d{4}\s?\d{4}\s?\d{4}        → [MASKED-{sha256[:8]}]
Rule 3: GSTIN  NEVER masked (public business data)
Applied: before every DB write AND before every LLM API call
```

### HTTPS & Headers
- AWS ALB terminates TLS. All HTTP redirected to HTTPS.
- Security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Strict-Transport-Security`.
- CORS: restrict to frontend domain only.

### DPDP Act 2023 Compliance Checklist
- [x] All data stored in ap-south-1 (India)
- [x] Explicit WhatsApp consent with timestamp and STOP support
- [x] PII (PAN, Aadhaar) masked before storage
- [x] Benchmark data requires explicit opt-in consent
- [x] Audit trail logs for all data access
- [x] Data deletion on org cascade-delete

---

## 8. Deployment Architecture

### Local Development (docker-compose.yml)
```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: ca_platform
      POSTGRES_PASSWORD: devpass
    ports: ["5432:5432"]

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]

  backend:
    build: ./backend
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    depends_on: [postgres, redis]
    ports: ["8000:8000"]

  worker-ocr:
    build: ./backend
    command: celery -A app.celery_app worker -Q ocr -c 2
    depends_on: [postgres, redis]

  worker-heavy:
    build: ./backend
    command: celery -A app.celery_app worker -Q heavy -c 4
    depends_on: [postgres, redis]

  worker-llm:
    build: ./backend
    command: celery -A app.celery_app worker -Q llm -c 2
    depends_on: [postgres, redis]

  worker-whatsapp:
    build: ./backend
    command: celery -A app.celery_app worker -Q whatsapp -c 2
    depends_on: [postgres, redis]

  beat:
    build: ./backend
    command: celery -A app.celery_app beat --loglevel=info
    depends_on: [redis]

  frontend:
    build: ./frontend
    command: npm run dev
    ports: ["3000:3000"]
```

### Production (AWS ECS Fargate)
- **ECS Services**: api (2 tasks), worker-ocr, worker-heavy, worker-llm, worker-whatsapp, beat (1 task each)
- **RDS**: PostgreSQL 16, db.r6g.large, Multi-AZ, 7-day backups
- **ElastiCache**: Redis 7, cache.t3.medium
- **S3**: Private bucket, versioning enabled, lifecycle: move to Glacier after 90 days
- **ALB**: HTTPS termination, HTTP→HTTPS redirect
- **Secrets Manager**: All credentials
- **CloudWatch**: Centralized logging, alarms on task failures
