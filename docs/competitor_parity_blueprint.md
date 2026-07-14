# CA Copilot Competitor-Parity Blueprint

This blueprint converts the requested CAGos, CA OMS, Practive/Practicore, and CaSync-style scope into a buildable CA Copilot roadmap.

## Product Positioning

CA Copilot should be a full CA practice operating system with an AI execution layer:

- Practice CRM, client onboarding, document collection, task workflows, billing, and team operations.
- Compliance calendar, GST/TDS/income-tax/company-law tracking, reminders, and reviewer sign-off.
- Tally/Excel/PDF ingestion with exception detection and partner review queues.
- Drafting and generation for notices, certificates, audit papers, proposals, and client follow-ups.
- Client portal and WhatsApp-first communication.
- Analytics for profitability, workload, SLA risk, client health, and compliance exposure.

## Feature Coverage Target

| Area | Required Capability |
| --- | --- |
| Client CRM | Client master, contacts, entity details, GSTIN/CIN/PAN/TAN fields, groups, tags, relationship managers, notes, and document vault. |
| Work Management | Task templates, recurring jobs, due dates, priority, staff assignment, review stages, checklists, comments, attachments, status history, and workload board. |
| Compliance | Statutory calendar, client-specific applicability, risk score, filing status, evidence links, partner approval, escalations, and WhatsApp/email reminders. |
| Document Management | Foldered vault, direct upload, OCR, metadata extraction, versioning, reviewer sign-off, retention labels, and S3-backed storage. |
| Tally/Excel Intake | Tally CSV import, Tally HTTP connector, Excel upload, normalization, validation errors, mapping preview, and import audit trail. |
| GST & Reconciliation | 2B/2A/books reconciliation, variance buckets, vendor summaries, tax exposure, follow-up generation, and exportable workpapers. |
| AI Exceptions | Morning partner inbox, severity, financial exposure, due dates, evidence, recommended actions, review decisions, and client follow-ups. |
| Certificates | Certificate templates, source validation, draft DOCX/PDF generation, maker-checker flow, and final register. |
| Audit | Working paper generation, anomaly detection, invoice fraud checks, materiality flags, audit trails, and review notes. |
| Practice Billing | Fee plans, recurring bills, invoices, collections, outstanding ageing, write-offs, and profitability by client/service. |
| Team & HR | Staff profiles, roles, attendance/timesheets, utilization, task capacity, article assignments, and productivity reports. |
| Client Portal | Secure login, document requests, uploads, task status, approvals, messages, and compliance view. |
| Communication | WhatsApp templates, reminders, bulk sends, inbound logs, email-ready drafts, client follow-up queue, and message audit trail. |
| Reports | Client health, pending tasks, due dates, billing, collections, staff utilization, GST variance, compliance risk, and partner dashboard. |
| Admin & Security | Multi-tenant orgs, RBAC, permissions, audit logs, data export, backups, encryption posture, and production secret handling. |

## Frontend Experience Standard

- Command-center first screen with portfolio risk, deadlines, workload, collections, and AI exceptions.
- Left navigation grouped by workflow, not a flat module dump.
- Every module should have search, filters, saved views, quick actions, empty states, loading states, and export actions.
- Dense professional UI for repeated office use: restrained colors, compact data tables, clear status badges, and fast scanning.
- Maker-checker flows must be visible everywhere a CA output is generated.

## MVP Build Order

1. Practice foundation: client CRM, task/job management, document vault, compliance calendar, team roles.
2. Revenue workflows: GST reconciliation, MSME 43B(h), drawing power, certificates, notices.
3. AI layer: Exception Autopilot, natural-language query, audit papers, anomaly and invoice fraud checks.
4. Operations layer: billing, collections, staff workload, timesheet profitability, reports.
5. Client-facing layer: client portal, WhatsApp automation, approval links, document request flows.

## Current Repo Fit

Already present:

- FastAPI backend, tenant middleware, auth, users, clients, documents, reconciliation, deadlines, WhatsApp, notices, audit papers, anomalies, invoices, query, benchmarking, Autopilot, and advanced automation routes.
- Next.js dashboard pages for most CA-specific modules.
- Tally connector for CSV and local Tally HTTP ingestion.
- Celery queues for OCR, heavy processing, LLM work, and WhatsApp.

Missing or needs expansion:

- Full task/job management module. Added MVP `/work` APIs and Work & Daybook UI.
- Billing, invoicing, collections, and fee ledger. Added MVP `/billing` APIs and Billing & Collections UI.
- Client portal. Added MVP `/portal` contact/request APIs and Client Portal UI.
- Team capacity, attendance, utilization, and HR workflows. Added MVP `/team` APIs and Team & Attendance UI.
- DSC/password/credential vault. Added MVP `/vault` APIs and DSC & Password Vault UI.
- Guided imports. Added MVP `/imports` validation/commit APIs and Guided Imports UI.
- Stronger reports and saved views. Added MVP `/reports` APIs and Reports & Saved Views UI.
- Remaining polish: global search, notifications, real payment gateway, real portal authentication, encrypted secret provider integration, and deeper mobile/client-facing flows.
