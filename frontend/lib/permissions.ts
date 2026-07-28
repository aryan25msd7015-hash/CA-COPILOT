/**
 * Four-tier access catalog.
 *
 * Firm JWT roles (DB): partner | manager | article
 *   partner  = Firm Head / Partner
 *   manager  = CA (Manager)
 *   article  = Intern / Staff
 *
 * Client = separate portal auth context (not a users.role).
 */
import { Role } from '@/types';

export const TIER_LABELS: Record<string, string> = {
  client: 'Client',
  article: 'Intern / Staff',
  manager: 'CA (Manager)',
  partner: 'Firm Head / Partner',
};

export const ALL_ACCESS: Role[] = ['partner'];
export const MANAGER_PLUS: Role[] = ['partner', 'manager'];
export const STAFF_PLUS: Role[] = ['partner', 'manager', 'article'];

/** Module UI access (sidebar + page shell). */
export const FEATURE_ROLES: Record<string, Role[]> = {
  command_center: STAFF_PLUS,
  exception_autopilot: STAFF_PLUS,
  ask_ca_copilot: STAFF_PLUS,
  clients_crm: STAFF_PLUS,
  work_daybook: STAFF_PLUS,
  document_vault: STAFF_PLUS,
  compliance_calendar: STAFF_PLUS,
  whatsapp_desk: STAFF_PLUS,
  client_portal_admin: MANAGER_PLUS,
  guided_imports: STAFF_PLUS,
  litigation_tracker: STAFF_PLUS,
  engagement_kyc: STAFF_PLUS,
  gst_reconciliation: STAFF_PLUS,
  msme_43bh: STAFF_PLUS,
  drawing_power: STAFF_PLUS,
  ca_certificates: STAFF_PLUS,
  mca_secretarial: STAFF_PLUS,
  lease_intelligence: STAFF_PLUS,
  tds_tcs_reconciliation: STAFF_PLUS,
  roc_xbrl_tracker: STAFF_PLUS,
  einvoice_irn: STAFF_PLUS,
  audit_papers: STAFF_PLUS,
  anomalies: STAFF_PLUS,
  invoice_scanner: STAFF_PLUS,
  notice_drafter: STAFF_PLUS,
  query_observation_ledger: STAFF_PLUS,
  statutory_checklist: STAFF_PLUS,
  logic_audit_layer1: STAFF_PLUS,
  causal_risk_layer3: STAFF_PLUS,
  ai_audit_orchestrator: STAFF_PLUS,
  billing_collections: MANAGER_PLUS,
  team_attendance: STAFF_PLUS,
  dsc_password_vault: ALL_ACCESS,
  reports_saved_views: STAFF_PLUS,
  readiness_diagnostics: MANAGER_PLUS,
  peer_review_qc: ALL_ACCESS,
  sop_knowledge_base: STAFF_PLUS,
  benchmarking: ALL_ACCESS,
  rfp_bids: ALL_ACCESS,
  profitability_audit: ALL_ACCESS,
  client_risk_scoring: MANAGER_PLUS,
  virtual_cfo_mis: MANAGER_PLUS,
};

/** Button / mutation gating. */
export const ACTION_PERMISSIONS: Record<string, Role[]> = {
  'export:reconciliation': MANAGER_PLUS,
  'approve:notice_draft': ALL_ACCESS,
  'approve:working_paper': MANAGER_PLUS,
  'approve:certificate': MANAGER_PLUS,
  'send:whatsapp_manual': MANAGER_PLUS,
  'view:benchmarking': ALL_ACCESS,
  'upload:document': STAFF_PLUS,
  'manage:users': ALL_ACCESS,
  'clear:fraud_flag': ALL_ACCESS,
  'delete:client': ALL_ACCESS,
  'manage:vault': ALL_ACCESS,
  'approve:engagement': MANAGER_PLUS,
  'close:litigation': MANAGER_PLUS,
  'close:observation': MANAGER_PLUS,
  'signoff:checklist': MANAGER_PLUS,
  'manage:peer_review': ALL_ACCESS,
  'view:risk_score': MANAGER_PLUS,
};

export function canAccessFeature(role: Role | undefined, feature: string): boolean {
  if (!role) return false;
  return FEATURE_ROLES[feature]?.includes(role) ?? false;
}

export function canPerform(role: Role | undefined, action: string): boolean {
  if (!role) return false;
  return ACTION_PERMISSIONS[action]?.includes(role) ?? false;
}
