# Four-tier role access matrix (CA Copilot)

Canonical firm JWT roles: `partner` (Firm Head), `manager` (CA), `article` (Intern/Staff).  
**Client** is a separate portal auth context (`auth_context=portal`, `role=client`) — not a `users.role` value.

## Hierarchy

| Tier | DB / JWT | Authority |
|---|---|---|
| Client | portal JWT | Own data only — invoices, docs, deadlines, portal requests |
| Intern/Staff | `article` | Execute / draft / investigate — no sign-off, no strategic/financial |
| CA (Manager) | `manager` | Review, approve, sign, own client relationships |
| Firm Head | `partner` | Everything + firm financials, growth, security controls |

## Locked-down modules (partner-only)

- DSC & Password Vault
- Benchmarking
- RFP Bids
- Profitability Audit
- Peer Review / QC

## Sign-off gated to manager+ (API, not UI-only)

- CA Certificates, Audit Papers, Notice Drafter
- Engagement letter approval
- Litigation close
- Observation close
- Statutory checklist sign-off
- TDS recon approval

## Gap modules (this release) + access

| Module | Article | Manager | Partner | Client |
|---|---|---|---|---|
| Engagement & KYC/AML | Draft | Approve | Full | ✗ |
| Litigation Tracker | Log/update | Close | Full | ✗ |
| TDS/TCS Reconciliation | Execute | Approve | View | ✗ |
| Query & Observation Ledger | Raise/update | Close | Full | ✗ |
| Statutory Checklist Engine | Fill | Sign-off | Full | ✗ |
| ROC/XBRL Tracker | Execute | Review | View | ✗ |
| E-Invoice / IRN | Validate | Review | View | ✗ |
| Peer Review / QC | ✗ | ✗ | Full | ✗ |
| SOP / Knowledge Base | Read / draft | Publish | Full | ✗ |
| Client Risk Scoring | ✗ | View/recompute | Full | ✗ |
| Virtual CFO / MIS | ✗ | Manage | Full | View published (future) |
| Client Portal (own) | ✗ | Admin | Full | **Primary interface** |

## Build sequence (priority)

1. RBAC catalog + nav gating (done)
2. Engagement & KYC/AML
3. Query & Observation Ledger
4. TDS/TCS Reconciliation
5. Litigation Tracker
6. Client Risk Scoring
7. Statutory Checklists
8. ROC/XBRL + E-Invoice/IRN
9. Peer Review / QC + SOP Knowledge Base
10. Virtual CFO / MIS
11. Client portal as distinct auth context

**Defer:** FEMA/RBI, valuation/DCF, multi-branch consolidation, Payroll & PF/ESI, Mobile Field Capture, E-Signature integration (Aadhaar eSign wiring).

## Enforcement surfaces

- `backend/app/utils/permissions.py` — FEATURE_ROLES + ACTION_PERMISSIONS
- `frontend/lib/permissions.ts` — UI mirror
- `require_feature` / `require_action` / `require_role` on APIs
- RLS `org_id` policies on gap tables (migration `040`)
- Portal middleware rejects portal JWTs on firm routes and firm JWTs on portal data routes
