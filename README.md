# CA Intelligence Platform

Multi-tenant SaaS for Indian CA firms. It covers client management, direct-to-S3
document ingestion, OCR, GST reconciliation, anomaly and invoice fraud checks,
compliance deadlines, WhatsApp reminders, health scores, notice drafting, audit
working papers, natural-language reporting, and consent-based benchmarking.

The integrated automation suite also includes:

- CA Exception Autopilot: a morning review inbox for Tally syncs, GST variance,
  MSME exposure, deadline risk, anomaly flags, certificates, leases, RFPs, and
  profitability leakage
- Advanced client-aware compliance calendar with filing risk scores
- MSME Section 43B(h) vendor verification, violation scans, and Clause 22 export
- Drawing power computation with stock/debtor eligibility and PDF/XLSX exports
- Six CA certificate workflows with validation and DOCX generation
- MCA secretarial minutes, AGM notices, filing sheets, MGT-14 XML, and DOCX export
- Ind AS 116 lease extraction, verification, schedules, and XLSX export
- Credential-backed RFP eligibility checks and proposal generation
- Actual-activity versus timesheet profitability and utilization audit

## Exception Autopilot

Autopilot turns raw client data and module outputs into a partner-review queue:

- `POST /autopilot/tally/sync` imports Tally-style voucher rows.
- `POST /autopilot/refresh` generates or updates evidence-linked exceptions.
- `GET /autopilot/overview` returns exposure, estimated review effort, time
  saved, recent syncs, and the prioritized exception queue.
- `PATCH /autopilot/exceptions/{id}` records CA review decisions and updates
  linked source records where appropriate.
- `POST /autopilot/followups` drafts or sends client follow-ups.

The browser workspace is available at `http://localhost:3000/autopilot`.
The lightweight Windows-friendly connector lives in `tally_connector/` and can
push either Tally CSV exports or vouchers fetched from a local Tally HTTP server.

## Stack

- FastAPI, SQLAlchemy, Alembic, Celery, PostgreSQL with pgvector, Redis
- Next.js 14, TypeScript, Tailwind CSS, TanStack Query, AG Grid
- Optional integrations: AWS S3, Azure Document Intelligence, Anthropic/OpenAI,
  and Meta WhatsApp Business API

## Local Setup

1. Ensure Docker Desktop is running.
2. Create local environment settings:

   ```powershell
   Copy-Item backend/.env.example backend/.env
   ```

3. Set `SECRET_KEY`, `S3_BUCKET`, and any integration credentials in
   `backend/.env`.
4. Start the nine-service development stack:

   ```powershell
   docker compose up --build
   ```

5. Apply migrations and seed deadlines:

   ```powershell
   docker compose exec backend alembic upgrade head
   docker compose exec backend python scripts/seed_compliance_deadlines.py
   ```

6. Populate the existing demo account with representative data:

   ```powershell
   docker compose exec backend python scripts/seed_demo_data.py
   ```

7. Open the frontend at `http://localhost:3000` and sign in with:

   - ID: `demo@cacopilot.in`
   - Passkey: `DemoPass@2026`

   You can also register a new firm for a clean workspace.
   API documentation is available at `http://localhost:8000/docs`.

## Validation

```powershell
docker compose exec backend pytest -q
docker compose exec frontend npm run build
docker compose config --quiet
```

## Important Environment Variables

`DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `S3_BUCKET`, `AWS_REGION`,
`AZURE_DOC_ENDPOINT`, `AZURE_DOC_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`, `WHATSAPP_VERIFY_TOKEN`, `FRONTEND_URL`,
and `ENV`.

Without optional provider credentials, the core application remains available,
but the corresponding OCR, LLM, storage, or WhatsApp workflow cannot complete.

## Production Notes

- Store secrets in AWS Secrets Manager and set `ENV=production`.
- Use separate least-privilege application and migration database roles.
- Terminate TLS at the load balancer and restrict backend ingress.
- Run Alembic migrations before deploying application tasks.
- Configure S3 CORS for direct browser uploads from the frontend origin.
- Retain database backups and application audit logs according to firm policy.
