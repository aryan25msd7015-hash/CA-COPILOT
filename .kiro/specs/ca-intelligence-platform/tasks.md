# Implementation Plan: CA Intelligence Platform

## Overview

Full-stack build of the CA Intelligence Platform — a multi-tenant SaaS for Indian CA firms. The platform includes a Python/FastAPI backend, Celery async workers, PostgreSQL with pgvector, a Next.js 14 frontend, and integrations with Azure OCR, Anthropic Claude, Meta WhatsApp Business API, and AWS S3.

## Tasks

- [ ] 1. Project Scaffold & Docker Compose Setup
  - Create `backend/` directory with `app/` package structure (models, schemas, routers, services, engines, tasks, utils, middleware)
  - Create `backend/requirements.txt` with pinned deps: fastapi==0.111.0, uvicorn==0.30.0, sqlalchemy==2.0.30, alembic==1.13.1, celery==5.4.0, redis==5.0.4, psycopg2-binary==2.9.9, python-jose==3.3.0, passlib==1.7.4, bcrypt==4.1.3, boto3==1.34.0, anthropic==0.28.0, openai==1.30.0, rapidfuzz==3.9.0, scikit-learn==1.5.0, pandas==2.2.2, numpy==1.26.4, scipy==1.13.0, python-docx==1.1.2, openpyxl==3.1.4, azure-ai-documentintelligence==1.0.0, pgvector==0.3.2, python-multipart==0.0.9
  - Create `backend/app/main.py` with FastAPI app factory, CORS middleware, and router registration stubs for all 15 routers
  - Create `backend/app/config.py` with Settings class that loads secrets from AWS Secrets Manager with `.env` fallback for local dev
  - Create `backend/app/database.py` with SQLAlchemy async engine and session factory
  - Create `backend/app/celery_app.py` with Celery instance, Redis broker/backend, and 4-queue routing (ocr, heavy, llm, whatsapp)
  - Create `backend/Dockerfile` (python:3.11-slim, non-root user)
  - Create `docker-compose.yml` with services: postgres:16, redis:7-alpine, backend, worker-ocr, worker-heavy, worker-llm, worker-whatsapp, beat, frontend
  - Initialize `frontend/` as Next.js 14 App Router project with TypeScript via `npx create-next-app@latest`
  - Install frontend deps: ag-grid-react@31, ag-grid-community@31, @tanstack/react-query@5, axios@1.7, shadcn/ui, tailwindcss@3
  - _Requirements: R18, R19_

- [ ] 2. Database Schema & Alembic Migrations
  - Create `backend/alembic/alembic.ini` and `backend/alembic/env.py` wired to the SQLAlchemy engine
  - Create `backend/app/models/__init__.py` importing all models
  - Create `backend/app/models/organization.py` — Organization ORM model
  - Create `backend/app/models/user.py` — User model with role CHECK (partner/manager/article), last_active_at
  - Create `backend/app/models/client.py` — Client model with all fields: gstin, whatsapp_number, whatsapp_consent_at, health_score, industry, benchmark_consent_at
  - Create `backend/app/models/document.py` — Document model with status/source enums, celery_task_id
  - Create `backend/app/models/transaction.py` — Transaction model with match_status, match_confidence, anomaly_score, fraud_flag, fingerprint
  - Create `backend/app/models/legal_chunk.py` — LegalChunk with pgvector Vector(1536) embedding column
  - Create `backend/app/models/compliance_deadline.py` — ComplianceDeadline with filing_type, period, deadline, status, filed_at, doc_required
  - Create `backend/app/models/whatsapp_reminder.py` — WhatsAppReminder model
  - Create `backend/app/models/reconciliation.py` — ReconciliationConfig and ReconciliationResult models
  - Create `backend/app/models/health_history.py` — ClientHealthHistory with score, tier, components JSONB
  - Create `backend/app/models/anomaly_flag.py` — AnomalyFlag with flag_type, risk_score, details JSONB, reviewed bool
  - Create `backend/app/models/saved_query.py` — SavedQuery model
  - Create initial Alembic migration `001_initial_schema.py` with full DDL from design section 4 including all indexes, pgvector IVFFlat index, and all CHECK constraints
  - _Requirements: R1, R2, R3, R4, R6, R7, R8, R9, R10, R11, R13, R14, R15, R16, R20_

- [ ] 3. Authentication & Tenant Middleware
  - Create `backend/app/utils/jwt_utils.py` — sign/verify JWTs containing org_id, user_id, role; raise HTTP 401 on invalid/expired tokens; support access tokens (15min) and refresh tokens (7d)
  - Create `backend/app/middleware/tenant.py` — extract org_id and role from JWT Bearer header, attach to request.state; skip middleware for /auth/*, /whatsapp/webhook, /consent/* paths
  - Create `backend/app/utils/scoped_query.py` — `scoped(db, Model, org_id)` that validates Model has org_id attribute before applying filter; raise RuntimeError if not
  - Create `backend/app/utils/deps.py` — FastAPI dependencies: get_db(), get_current_user(), require_role(allowed_roles: list)
  - Create `backend/app/schemas/auth.py` — Pydantic schemas: RegisterRequest, LoginRequest, TokenResponse, UserOut
  - Create `backend/app/routers/auth.py` — POST /auth/register (create org + partner user, return tokens), POST /auth/login, POST /auth/refresh, POST /auth/logout
  - Create `backend/app/routers/users.py` — GET/POST/PATCH/DELETE /users endpoints all requiring partner role
  - _Requirements: R1, R2_

- [ ] 4. Client Management API
  - Create `backend/app/schemas/client.py` — ClientCreate, ClientUpdate, ClientOut, ClientListOut Pydantic schemas
  - Create `backend/app/routers/clients.py` with all endpoints using scoped() helper:
    - GET /clients — list all clients in org sorted by health_score ASC
    - POST /clients — create client scoped to org_id
    - GET /clients/{id} — client detail, 404 if not in org
    - PATCH /clients/{id} — update client fields
    - DELETE /clients/{id} — partner only
    - GET /clients/{id}/health-history — last 30 records
  - Create `backend/app/routers/organizations.py` — GET /organizations/me, PATCH /organizations/me (partner only)
  - _Requirements: R1, R2, R11_

- [ ] 5. S3 Document Upload & Task Status API
  - Create `backend/app/services/s3_service.py` with: generate_presigned_put_url(bucket, key, content_type, expires=300), generate_presigned_get_url(bucket, key, expires=3600), upload_bytes(bucket, key, data), download_bytes(bucket, key)
  - Create `backend/app/schemas/document.py` — UploadUrlRequest, UploadUrlResponse, DocumentOut Pydantic schemas
  - Create `backend/app/routers/documents.py`:
    - POST /documents/upload-url — validate doc_type enum, build S3 key as {org_id}/{client_id}/{uuid4()}.{ext}, create Document record status=pending, return {upload_url, document_id}
    - GET /documents — list with filters: client_id, doc_type, status; paginated
    - GET /documents/{id} — document detail with ocr_json
    - POST /documents/{id}/retry-ocr — re-enqueue OCR Celery task
  - Create `backend/app/routers/tasks.py` — GET /tasks/{celery_task_id}/status returning {state, result, error}
  - _Requirements: R3_

- [ ] 6. PII Masker Engine
  - Create `backend/app/engines/pii_masker.py`:
    - Compile regexes at module level: PAN_RE = `[A-Z]{5}[0-9]{4}[A-Z]`, AADHAAR_RE = `\d{4}\s?\d{4}\s?\d{4}`, GSTIN_RE = `\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]`
    - mask_pii(text: str) -> str — replace PAN and Aadhaar with [MASKED-{sha256[:8]}], skip GSTIN matches, deterministic hashing
    - unmask_count(text: str) -> dict — return counts of each PII type found before masking (for audit logs)
  - Create `backend/tests/test_pii_masker.py` with unit tests: PAN masked, Aadhaar masked, GSTIN NOT masked, same input produces same token (deterministic), text with no PII returns unchanged
  - _Requirements: R4_

- [ ] 7. Azure OCR Pipeline
  - Create `backend/app/tasks/ocr_tasks.py` with Celery tasks on queue='ocr':
    - run_ocr(document_id: str) — load Document, call Azure DocumentAnalysisClient.begin_analyze_document_from_url with prebuilt-invoice model, extract text/tables/kvs, apply mask_pii() to all text fields, save ocr_text and ocr_json to Document, set status=ocr_complete, chain to route_doc.delay(); on any exception set status=ocr_failed, log error; retry with exponential backoff max 3 times
    - route_doc(document_id: str) — dispatch to correct extractor based on doc_type: invoice→extract_invoice_transactions, purchase_register→extract_csv_transactions, gstr2b→extract_gstr2b, others→pass
    - extract_invoice_transactions(document_id: str) — parse OCR kvs into Transaction records, insert to DB
    - extract_csv_transactions(document_id: str) — decode ocr_text as CSV, run tally_normalizer, insert Transaction records; set Document status=processed or parse_failed
    - extract_gstr2b(document_id: str) — parse GSTR-2B JSON from ocr_json, validate schema, insert Transaction records with source=gstr2b
  - _Requirements: R4, R19_

- [ ] 8. Tally CSV Normalizer
  - Create `backend/app/engines/tally_normalizer.py`:
    - TALLY_MAP dict covering all Tally Prime headers (Voucher No, Date, Party Name, Amount, GSTIN/UIN of Party) and Tally ERP 9 headers (Vch No., Particulars, Debit) mapped to canonical names
    - normalize_tally(df: pd.DataFrame) -> pd.DataFrame — rename columns, parse dates dayfirst=True, strip commas from amounts, coerce numeric dropping NaN, normalize vendor_name (uppercase, strip, remove PVT/LTD/PRIVATE/LIMITED/LLP suffixes), validate required fields present
    - to_canonical_csv(transactions: list[dict]) -> str — serialize Transaction list back to canonical CSV with headers: invoice_no, vendor_name, vendor_gstin, amount, date
  - Create `backend/tests/test_tally_normalizer.py` — tests: Prime headers normalize, ERP9 headers normalize, round-trip parse→serialize→re-parse produces equivalent records, rows with unparseable amounts are dropped, vendor name suffix stripping works
  - _Requirements: R5, R20_

- [ ] 9. GST Reconciliation Engine & API
  - Create `backend/app/engines/reconciliation_engine.py`:
    - normalize(df: pd.DataFrame) -> pd.DataFrame — invoice_no uppercase strip, vendor_name normalize, date parse, amount round(2)
    - reconcile(purchase_df, gstr2b_df, config: dict) -> tuple[pd.DataFrame, pd.DataFrame] — Tier 1 exact (gstin+invoice+amount), Tier 2 tolerance (gstin exact, amount ±tol, date ±days), Tier 3 fuzzy (token_sort_ratio ≥ threshold, amount ±tol); return (matched_df with match_type/confidence cols, unmatched_df)
  - Create `backend/app/tasks/reconciliation_tasks.py` with run_reconciliation(client_id, period) on queue=heavy: load transactions, load config, run engine, update transaction match_status/confidence in DB, insert ReconciliationResult, chain to run_anomaly_detection.delay(client_id)
  - Create `backend/app/schemas/reconciliation.py` — ReconciliationRunRequest, ReconciliationResultOut, ReconciliationConfigOut/Update
  - Create `backend/app/routers/reconciliation.py`: POST /reconciliation/run (returns task_id), GET /reconciliation/results/{client_id}, GET /reconciliation/transactions (paginated+filtered), GET+PUT /reconciliation/config/{client_id}, GET /reconciliation/export/{result_id} (returns Excel file stream)
  - Create `backend/app/utils/export_utils.py` — build_reconciliation_excel(matched_df, unmatched_df) -> bytes using openpyxl
  - _Requirements: R6_

- [ ] 10. Anomaly Detection Engine & API
  - Create `backend/app/engines/anomaly_detector.py`:
    - BENFORD constant = [0.301,0.176,0.125,0.097,0.079,0.067,0.058,0.051,0.046]
    - train_isolation_forest(transactions: pd.DataFrame) -> tuple — group by vendor_gstin, fit IsolationForest(contamination=0.02, random_state=42) on [mean, std, count] features
    - score_transaction(model, stats_df, vendor_gstin, amount) -> float — 0.75 for unknown vendor, else normalized decision_function (0-1 scale)
    - benford_test(amounts: list) -> dict — compute first-digit distribution, chi-square vs BENFORD, return {chi2, p_value, suspicious: p_value < 0.05}
    - flag_rule_anomalies(df: pd.DataFrame) -> pd.DataFrame — add columns: flag_round, flag_weekend, flag_duplicate, flag_threshold, risk_flags score
    - detect_vendor_spikes(client_id, db) -> list[dict] — compare current 3-month vs prior monthly average, flag > 3x increase
  - Create `backend/app/tasks/anomaly_tasks.py` — run_anomaly_detection(client_id) on queue=heavy: train/score all transactions, run all rule checks, run benford test, insert AnomalyFlag records, update transactions.anomaly_score
  - Create `backend/app/routers/anomalies.py`: GET /anomalies, GET /anomalies/client/{id}, PATCH /anomalies/{flag_id}/review
  - _Requirements: R7, R13_

- [ ] 11. Smart Deadline Engine & WhatsApp Scheduler
  - Create `backend/app/engines/deadline_engine.py`:
    - compute_days_before_alert(client_id, filing_type, db) -> int — load last 12 filings, compute avg_days_late, return 12 if ≥5, 9 if ≥2, 5 if on-time, 7 if <3 history records
    - deadline_health_component(client_id, db) -> float — on_time_count / total_last_12 filings
  - Create `backend/scripts/seed_compliance_deadlines.py` — populate standard Indian filing deadlines (GSTR-1 11th, GSTR-3B 20th, TDS 24Q/26Q quarterly, Advance Tax quarterly) for current + next financial year
  - Create `backend/app/tasks/whatsapp_tasks.py`:
    - morning_reminder_check() Celery Beat task at 09:00 IST: get deadlines within 10 days, for each check consent/doc_received/reminder_count/one_per_day, pick template (filing_deadline_urgent if ≤1 day else data_request_reminder), call send_whatsapp_template.delay(), log to whatsapp_reminders
    - send_whatsapp_template(phone, template, params) — queue=whatsapp, call Meta Business API
    - process_incoming_wa(payload) — extract message, find client by phone, on document: download_media→upload S3→create Document→run_ocr.delay(), on STOP: set consent_at=NULL, on unknown: send guidance text
  - Create `backend/app/routers/deadlines.py`: GET /deadlines, POST /deadlines, PATCH /deadlines/{id}, GET /deadlines/client/{client_id}
  - Add Celery Beat schedule entry for morning_reminder_check at crontab(hour=9, minute=0, tz=IST)
  - _Requirements: R8_

- [ ] 12. WhatsApp Pipeline API
  - Create `backend/app/services/whatsapp_service.py`:
    - send_template(phone, template, params) — POST to Meta Business API graph endpoint
    - send_text(phone, body) — free-form message within 24h window
    - download_media(media_id) -> bytes — GET media URL from Meta API, download bytes
    - generate_consent_token(client_id) -> str — HMAC-SHA256 signed token with 24h TTL
    - verify_consent_token(token) -> str — returns client_id or raises HTTPException 400
  - Create `backend/app/routers/whatsapp.py`:
    - GET /whatsapp/consent/{token} — no auth required; verify token, set client.whatsapp_consent_at=NOW(), return HTML confirmation page
    - GET+POST /whatsapp/webhook — GET: return hub.challenge for Meta verification; POST: return {"status":"ok"} immediately (<200ms), process via FastAPI BackgroundTasks calling process_incoming_wa()
    - POST /whatsapp/send-manual — partner/manager only; send one-off message
    - GET /whatsapp/status — all clients with doc submission status per filing period and reminder history
  - _Requirements: R9_

- [ ] 13. Legal KB & RAG Notice Drafter
  - Create `backend/app/engines/rag_drafter.py`:
    - NOTICE_RE dict with compiled regexes for notice_type, section, AY, demand_amount, due_date
    - build_knowledge_base(docs: list[tuple[str,str]]) — chunk PDFs with RecursiveCharacterTextSplitter(chunk_size=400, overlap=50), embed each chunk with text-embedding-3-small, insert into legal_chunks table
    - retrieve_legal_context(notice_text, k=5, db) -> list[str] — embed query, pgvector cosine similarity: SELECT content FROM legal_chunks ORDER BY embedding <=> query_vec LIMIT k
    - parse_notice(text: str) -> dict — regex extract all NOTICE_RE fields
    - draft_reply(notice_data, chunks, anthropic_client) -> dict — Claude generation with strict system prompt (only cite sections in context, no invented case laws, flag insufficient context as "CA REVIEW REQUIRED")
    - validate_citations(draft, context) -> dict — extract all "Section X" refs from draft, check each exists verbatim in context, return {valid, unverified, confidence}
  - Create `backend/app/tasks/llm_tasks.py`:
    - generate_notice_draft(document_id) on queue=llm — full RAG pipeline; on Anthropic error retry with OpenAI; store result as JSON in Document.ocr_json under key "draft_result"
    - generate_audit_papers(document_id) on queue=llm — audit papers pipeline
    - run_nl_query(question, org_id) on queue=llm — NL query pipeline
  - Create `backend/app/routers/notices.py`: POST /notices/draft (returns task_id), GET /notices/draft/{task_id}, GET /notices
  - Create `backend/scripts/build_legal_kb.py` — one-time script to index legal PDFs
  - _Requirements: R10_

- [ ] 14. Client Health Score Engine
  - Create `backend/app/engines/health_score_engine.py`:
    - compute_health_score(client_id, db) -> dict — five components: gst_score=deadline_health_component*25, itc_score=max(0,25*(1-min(itc_gap_pct*5,1))), notice_score=max(0,25-open_notices*8), anomaly_score_comp=max(0,15*(1-min(anomaly_rate*10,1))), tds_score=tds_on_time_rate*10; total=round(sum); tier=green/amber/red
    - get_itc_gap_pct(client_id, db) -> float — unmatched_value / total_value from latest reconciliation
    - get_anomaly_rate(client_id, db) -> float — flagged transactions / total transactions (last 3 months)
    - get_tds_compliance_rate(client_id, db) -> float — on-time TDS filings / total TDS deadlines
  - Create `backend/app/tasks/health_tasks.py` — recompute_all_health_scores() Celery Beat at 02:00 IST: iterate all clients, compute_health_score(), update clients.health_score, insert ClientHealthHistory record
  - Create `backend/app/routers/health_scores.py`: GET /health-scores (all clients sorted by score), POST /health-scores/recompute/{client_id}
  - Add beat schedule entry for recompute_all_health_scores at crontab(hour=2, minute=0)
  - _Requirements: R11_

- [ ] 15. AI Audit Working Papers
  - Create `backend/app/engines/audit_papers_engine.py`:
    - parse_trial_balance(df: pd.DataFrame) -> dict — rename debit/credit/account/group columns, compute net per row, aggregate totals by group (Assets, Liabilities, Revenue, Expenses), return summary dict with accounts list
    - compute_ratios(tb: dict) -> dict — current_ratio, debt_equity_ratio, gross_margin_pct, net_margin_pct, asset_turnover; handle division by zero
    - generate_audit_observations(tb, ratios, anomalies, anthropic_client) -> str — Claude prompt with ICAI format instructions (OBSERVATION/AREA/RISK LEVEL/FINDING/IMPLICATION/RECOMMENDATION structure), 5-8 observations on material items
    - export_working_paper(client_name, observations, ratios, period) -> bytes — build DOCX with python-docx: title heading, date, ratios table, observations section; return bytes for S3 upload
  - Add generate_audit_papers(document_id) Celery task in llm_tasks.py on queue=llm
  - Create `backend/app/routers/audit_papers.py`: POST /audit-papers/generate (returns task_id), GET /audit-papers/{task_id}, GET /audit-papers/export/{id} (stream DOCX)
  - _Requirements: R12_

- [ ] 16. Invoice Fraud Scanner
  - Create `backend/app/engines/invoice_fraud_scanner.py`:
    - validate_gstin(gstin: str) -> dict — GET https://online.mastergstin.com/api/v3.0/search?gstin={gstin} with 5s timeout; on timeout/error fall back to regex format check; return {valid, name, status, offline}
    - verify_invoice_tax(invoice_data: dict) -> dict — check CGST==SGST for intra-state (tolerance ₹1), check actual_rate is standard GST rate (0/5/12/18/28%), check total == base+taxes (tolerance ₹2); return {valid, issues}
    - generate_fingerprint(invoice_data: dict) -> str — SHA-256 of "vendor_gstin|invoice_no|amount|date"
    - check_duplicate(fingerprint, client_id, db) -> bool — query transactions.fingerprint
    - scan_invoice(transaction_id, db) — run all three checks; if any fail set transactions.fraud_flag with failure reason string
  - Add run_invoice_fraud_scan(document_id) Celery task chained after OCR for invoice doc_type
  - Create `backend/app/routers/invoices.py`: GET /invoices/fraud-queue (all fraud-flagged), PATCH /invoices/{id}/clear-flag (partner only)
  - _Requirements: R14_

- [ ] 17. Natural Language Query Engine
  - Create `backend/app/engines/nl_query_engine.py`:
    - SCHEMA_CONTEXT constant with all table/column descriptions from design section 6.8
    - STARTER_QUERIES list of 10 common CA queries
    - BLOCKED_KEYWORDS = ['DELETE','UPDATE','INSERT','DROP','TRUNCATE','ALTER','CREATE','GRANT','REVOKE']
    - translate_to_sql(question, org_id, anthropic_client) -> str — Claude with schema context + org_id injection in system prompt; return only SQL
    - validate_sql(sql: str) — raise ValueError if any BLOCKED_KEYWORDS found in sql.upper()
    - execute_query(sql, org_id, db) -> dict — SQLAlchemy text() with parameterized org_id, return {sql, rows: list[dict], row_count}
  - Add run_nl_query(question, org_id) to llm_tasks.py on queue=llm
  - Create `backend/app/routers/query.py`: POST /query/ask, GET /query/saved, POST /query/saved, DELETE /query/saved/{id}
  - _Requirements: R15_

- [ ] 18. Benchmarking Engine
  - Create `backend/app/engines/benchmarking_engine.py`:
    - get_benchmark_pool(industry, exclude_org_id, db) -> list — query clients WHERE benchmark_consent_at IS NOT NULL AND org_id != exclude_org_id AND industry = industry
    - compute_industry_benchmarks(industry, exclude_org_id, db) -> dict | None — return None if pool < 5; compute median/p25/p75 per ratio using pandas quantile
    - compare_client(client_id, db) -> dict — get client ratios from latest trial balance, get benchmarks for client.industry, return {client_ratios, benchmarks, peer_count}
  - Create `backend/app/routers/benchmarking.py`: GET /benchmarking/{client_id} (premium plan only — check org.plan=='premium'), POST /benchmarking/consent
  - _Requirements: R16_

- [ ] 19. Frontend — Auth, Layout & RBAC
  - Create `frontend/lib/api.ts` — axios instance with baseURL from env, request interceptor to attach `Authorization: Bearer {token}` from localStorage, response interceptor to redirect to /login on 401
  - Create `frontend/lib/auth.ts` — login(email, password): call API, store tokens; logout(): clear tokens, redirect; getAccessToken(): return from localStorage
  - Create `frontend/hooks/useAuth.ts` — React context + hook returning {user, isLoading, login, logout}; decode JWT to get role/org_id
  - Create `frontend/hooks/usePermission.ts` — PERMS map: {'export:reconciliation':['partner','manager'], 'approve:notice_draft':['partner'], 'send:whatsapp_manual':['partner','manager'], 'view:benchmarking':['partner'], 'upload:document':['partner','manager','article']}; usePermission(action) -> boolean
  - Create `frontend/app/(auth)/login/page.tsx` — email+password form, TanStack Query mutation, error display
  - Create `frontend/app/(auth)/register/page.tsx` — org name + email + password form
  - Create `frontend/app/(dashboard)/layout.tsx` — sidebar with role-filtered nav links, topbar with user info and logout, redirect to /login if no valid token
  - _Requirements: R17, R2_

- [ ] 20. Frontend — Client Dashboard & Health Scores
  - Create `frontend/components/clients/HealthBadge.tsx` — badge component: score < 50 → red bg "High Risk", 50-74 → amber "Needs Attention", ≥75 → green "Healthy"
  - Create `frontend/components/clients/ClientTable.tsx` — AG Grid table with columns: name, gstin, health_score (HealthBadge renderer), pending_docs count, last_reconciliation_date; sorted red-first by default
  - Create `frontend/app/(dashboard)/page.tsx` — homepage: summary cards (total clients, red/amber/green counts), ClientTable
  - Create `frontend/app/(dashboard)/clients/page.tsx` — full client list with search/filter
  - Create `frontend/app/(dashboard)/clients/[id]/page.tsx` — client detail: health score gauge, 3-month score sparkline, open deadlines list, recent transactions, anomaly count badge
  - _Requirements: R11, R17_

- [ ] 21. Frontend — Document Upload & WhatsApp Status
  - Create `frontend/components/shared/FileUploadZone.tsx` — drag-and-drop zone: call POST /documents/upload-url, then PUT bytes directly to S3 pre-signed URL; show upload progress; on complete show TaskStatusPoller
  - Create `frontend/components/shared/TaskStatusPoller.tsx` — polls GET /tasks/{task_id}/status every 3s; renders progress spinner with status text; stops on SUCCESS or FAILURE
  - Create `frontend/app/(dashboard)/documents/page.tsx` — document list AG Grid with status badge column, FileUploadZone at top, retry OCR button for ocr_failed docs
  - Create `frontend/components/whatsapp/WhatsAppStatusTable.tsx` — grid: rows=clients, columns=filing_types; cell shows doc status badge (received/pending/overdue); last reminder date; Send Reminder button (calls POST /whatsapp/send-manual, guarded by usePermission)
  - Create `frontend/app/(dashboard)/whatsapp/page.tsx` — WhatsApp operations page with WhatsAppStatusTable
  - _Requirements: R3, R9, R17_

- [ ] 22. Frontend — Reconciliation Grid & Anomaly Dashboard
  - Create `frontend/components/reconciliation/ReconciliationGrid.tsx` — AG Grid: columns invoice_no, vendor_name, vendor_gstin, amount, date, match_type (color-coded cell renderer: exact=green, tolerance=amber, fuzzy=yellow, unmatched=red), confidence%, anomaly_score (risk chip); toolbar with Run Reconciliation button, Export Excel button, Tolerance Settings drawer
  - Create `frontend/app/(dashboard)/reconciliation/page.tsx` — client selector, reconciliation grid, unmatched-only toggle filter
  - Create `frontend/app/(dashboard)/anomalies/page.tsx` — anomaly flags AG Grid: flag_type, risk_score, transaction details, reviewed checkbox; filter by type
  - Create `frontend/app/(dashboard)/invoices/page.tsx` — fraud queue AG Grid: invoice details, fraud_flag reason, Clear Flag button (partner only via usePermission)
  - Create `frontend/app/(dashboard)/deadlines/page.tsx` — compliance calendar grid: rows=clients, columns=upcoming filings; color-coded cells; click-to-mark-filed
  - _Requirements: R6, R7, R8, R13, R14, R17_

- [ ] 23. Frontend — AI Features
  - Create `frontend/app/(dashboard)/notices/page.tsx` — upload notice doc via FileUploadZone, trigger draft via POST /notices/draft, poll with TaskStatusPoller, display draft text with source chunks in collapsible panel, show citation validation warnings in amber banner
  - Create `frontend/app/(dashboard)/audit/page.tsx` — upload trial balance, trigger POST /audit-papers/generate, poll status, display ratios table and ICAI observations text, Download DOCX button
  - Create `frontend/app/(dashboard)/query/page.tsx` — NL query textarea, submit calls POST /query/ask, display generated SQL in collapsible code block, display results in AG Grid, Save Query button, starter queries sidebar list
  - Create `frontend/app/(dashboard)/benchmarking/page.tsx` — premium plan gate (show upgrade prompt if not premium); comparison table: metric, client value, industry median, industry p25/p75; peer count disclosure
  - _Requirements: R10, R12, R15, R16, R17_

- [ ] 24. Row-Level Security & Security Hardening
  - Create Alembic migration `002_rls_policies.py` — enable RLS on all multi-tenant tables, create USING (org_id = current_setting('app.current_org_id')::uuid) policy for each; add BYPASSRLS to the app service role so the app can SET LOCAL
  - Update `backend/app/database.py` session factory to execute `SET LOCAL app.current_org_id = :org_id` at the start of each request session using SQLAlchemy events
  - Add security headers middleware to `backend/app/main.py`: X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Strict-Transport-Security: max-age=31536000
  - Configure CORS in main.py to allow only FRONTEND_URL env var, not wildcard
  - Add last_active_at update on every authenticated request; add dep check that raises 401 if last_active_at > 30 days ago
  - Add audit logging middleware: log org_id, user_id, method, path, status_code, timestamp to structured JSON on every request
  - _Requirements: R18_

- [ ] 25. Integration Wiring & docker-compose Validation
  - Register all 15 routers in `backend/app/main.py` with correct prefixes and tags
  - Import all Celery task modules in `backend/app/celery_app.py` includes list for task autodiscovery
  - Add all Celery Beat entries to `celery_app.py`: morning_reminder_check at 09:00 IST, recompute_all_health_scores at 02:00 IST
  - Create `backend/app/services/secrets_service.py` — get_secret(name) using boto3 secretsmanager, with local fallback reading from .env file when AWS_REGION not set
  - Verify `docker-compose up` starts all 9 services without errors; fix any import or config issues
  - Create `README.md` with: prerequisites, local setup steps (docker-compose up, alembic upgrade head, seed script), environment variable list, first-run steps (create org via POST /auth/register), production deployment notes
  - _Requirements: R1-R20_

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": [1] },
    { "wave": 2, "tasks": [2, 19] },
    { "wave": 3, "tasks": [3, 6, 8, 20] },
    { "wave": 4, "tasks": [4, 5, 7, 9, 11, 13, 14, 15, 16, 17, 18, 21] },
    { "wave": 5, "tasks": [10, 12, 22] },
    { "wave": 6, "tasks": [23, 24] },
    { "wave": 7, "tasks": [25] }
  ],
  "dependencies": {
    "2":  ["1"],
    "3":  ["2"],
    "4":  ["3"],
    "5":  ["3"],
    "6":  ["2"],
    "7":  ["2", "6", "8"],
    "8":  ["2"],
    "9":  ["2"],
    "10": ["9"],
    "11": ["2"],
    "12": ["11"],
    "13": ["2"],
    "14": ["2"],
    "15": ["2"],
    "16": ["2"],
    "17": ["2"],
    "18": ["2"],
    "19": ["1"],
    "20": ["19"],
    "21": ["20"],
    "22": ["21"],
    "23": ["22"],
    "24": ["3","4","5","6","7","8","9","10","11","12","13","14","15","16","17","18"],
    "25": ["24","23"]
  }
}
```

## Notes

- All backend tasks run within the workspace directory `c:\Users\Aryan\OneDrive\Desktop\CA COPILOT\`
- Local dev uses Docker Compose; production targets AWS ECS Fargate in ap-south-1
- AWS Secrets Manager and Azure OCR credentials must be provided by the user before running tasks 7, 12, 13
- The legal knowledge base (Task 13) requires the user to supply legal PDF files before running build_legal_kb.py
- Tasks 1–18 are backend; Tasks 19–23 are frontend; Tasks 24–25 are cross-cutting
