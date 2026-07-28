"""
Four-tier role access for CA Copilot.

Canonical firm roles (DB / JWT):
  partner  → Firm Head / Partner
  manager  → CA (Manager)
  article  → Intern / Staff

Client is a *separate auth context* (portal JWT), not a users.role value.
"""

from __future__ import annotations

from typing import Iterable

# Display labels used in UI / docs
TIER_LABELS = {
    "client": "Client",
    "article": "Intern / Staff",
    "manager": "CA (Manager)",
    "partner": "Firm Head / Partner",
}

FIRM_ROLES = ("article", "manager", "partner")
ALL_ACCESS_ROLES = ("partner",)
MANAGER_PLUS = ("partner", "manager")
STAFF_PLUS = ("partner", "manager", "article")

# Feature → firm roles that may access the module UI / list APIs.
# Sign-off / destructive actions use finer ACTION_PERMISSIONS below.
FEATURE_ROLES: dict[str, tuple[str, ...]] = {
    # Command
  "command_center": STAFF_PLUS,
  "workspace_partner": ALL_ACCESS_ROLES,
  "workspace_ca": MANAGER_PLUS,
  "workspace_staff": STAFF_PLUS,
  "exception_autopilot": STAFF_PLUS,  # article: action assigned; manage=manager+    "ask_ca_copilot": STAFF_PLUS,
    # Practice
    "clients_crm": STAFF_PLUS,
    "work_daybook": STAFF_PLUS,
    "document_vault": STAFF_PLUS,
    "compliance_calendar": STAFF_PLUS,
    "whatsapp_desk": STAFF_PLUS,  # draft/assist; send=manager+
    "client_portal_admin": MANAGER_PLUS,
    "guided_imports": STAFF_PLUS,
    "litigation_tracker": STAFF_PLUS,
    "engagement_kyc": STAFF_PLUS,
    # Delivery
    "gst_reconciliation": STAFF_PLUS,
    "msme_43bh": STAFF_PLUS,
    "drawing_power": STAFF_PLUS,
    "ca_certificates": STAFF_PLUS,  # draft=article; sign=manager+
    "mca_secretarial": STAFF_PLUS,
    "lease_intelligence": STAFF_PLUS,
    "tds_tcs_reconciliation": STAFF_PLUS,
    "roc_xbrl_tracker": STAFF_PLUS,
    "einvoice_irn": STAFF_PLUS,
    # Assurance
    "audit_papers": STAFF_PLUS,
    "anomalies": STAFF_PLUS,
    "invoice_scanner": STAFF_PLUS,
    "notice_drafter": STAFF_PLUS,
    "query_observation_ledger": STAFF_PLUS,
    "statutory_checklist": STAFF_PLUS,
    "logic_audit_layer1": STAFF_PLUS,
    "causal_risk_layer3": STAFF_PLUS,
    "ai_auditor_layer4": STAFF_PLUS,
    "ai_audit_orchestrator": STAFF_PLUS,
    # Office
    "billing_collections": MANAGER_PLUS,  # partner=full financial; manager=own clients
    "team_attendance": STAFF_PLUS,  # article: own attendance; manage=manager+
    "dsc_password_vault": ALL_ACCESS_ROLES,  # partner-only lock-down
    "reports_saved_views": STAFF_PLUS,
    "readiness_diagnostics": MANAGER_PLUS,
    "peer_review_qc": ALL_ACCESS_ROLES,
    "sop_knowledge_base": STAFF_PLUS,
    # Growth
    "benchmarking": ALL_ACCESS_ROLES,
    "rfp_bids": ALL_ACCESS_ROLES,
    "profitability_audit": ALL_ACCESS_ROLES,
    "client_risk_scoring": MANAGER_PLUS,
    "virtual_cfo_mis": MANAGER_PLUS,
}

# Fine-grained actions (API / button gating)
ACTION_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "org:manage": ALL_ACCESS_ROLES,
    "team:manage": ALL_ACCESS_ROLES,
    "client:write": MANAGER_PLUS,
    "client:read": STAFF_PLUS,
    "client:delete": ALL_ACCESS_ROLES,
    "document:write": MANAGER_PLUS,
    "document:upload": STAFF_PLUS,
    "reconciliation:run": STAFF_PLUS,
    "reconciliation:approve": MANAGER_PLUS,
    "billing:manage": ALL_ACCESS_ROLES,
    "billing:view_client": MANAGER_PLUS,
    "audit:export": MANAGER_PLUS,
    "audit:sign": MANAGER_PLUS,
    "certificate:sign": MANAGER_PLUS,
    "notice:approve": ALL_ACCESS_ROLES,
    "working_paper:approve": MANAGER_PLUS,
    "fraud:clear": ALL_ACCESS_ROLES,
    "whatsapp:send": MANAGER_PLUS,
    "vault:manage": ALL_ACCESS_ROLES,
    "benchmarking:view": ALL_ACCESS_ROLES,
    "rfp:manage": ALL_ACCESS_ROLES,
    "profitability:view": ALL_ACCESS_ROLES,
    "assistant:ask": STAFF_PLUS,
    "engagement:approve": MANAGER_PLUS,
    "litigation:close": MANAGER_PLUS,
    "observation:close": MANAGER_PLUS,
    "checklist:signoff": MANAGER_PLUS,
    "peer_review:manage": ALL_ACCESS_ROLES,
    "risk_score:view": MANAGER_PLUS,
}


def role_allowed(role: str | None, allowed: Iterable[str]) -> bool:
    return bool(role) and role in set(allowed)


def can_access_feature(role: str | None, feature: str) -> bool:
    return role_allowed(role, FEATURE_ROLES.get(feature, ()))


def can_perform(role: str | None, action: str) -> bool:
    return role_allowed(role, ACTION_PERMISSIONS.get(action, ()))


def permissions_for_role(role: str) -> list[str]:
    return [action for action, roles in ACTION_PERMISSIONS.items() if role in roles]
