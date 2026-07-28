import { Role } from '@/types';
import { FEATURE_ROLES } from '@/lib/permissions';

export interface NavItem {
  href: string;
  label: string;
  feature: string;
  roles: Role[];
  keywords?: string[];
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

function item(href: string, label: string, feature: string, keywords: string[] = []): NavItem {
  return {
    href,
    label,
    feature,
    roles: FEATURE_ROLES[feature] || [],
    keywords,
  };
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Command',
    items: [
      item('/', 'Command Center', 'command_center', ['dashboard', 'home', 'overview']),
      item('/autopilot', 'Exception Autopilot', 'exception_autopilot', ['review', 'exceptions', 'inbox']),
      item('/query', 'Ask CA Copilot', 'ask_ca_copilot', ['search', 'nl query', 'ask']),
    ],
  },
  {
    title: 'Practice',
    items: [
      item('/clients', 'Clients & CRM', 'clients_crm', ['crm', 'client master']),
      item('/work', 'Work & Daybook', 'work_daybook', ['tasks', 'jobs', 'daybook']),
      item('/documents', 'Document Vault', 'document_vault', ['files', 'ocr', 'vault']),
      item('/deadlines', 'Compliance Calendar', 'compliance_calendar', ['due dates', 'calendar']),
      item('/whatsapp', 'WhatsApp Desk', 'whatsapp_desk', ['messages', 'reminders']),
      item('/portal', 'Client Portal', 'client_portal_admin', ['requests', 'approvals']),
      item('/imports', 'Guided Imports', 'guided_imports', ['tally', 'excel', 'mapping']),
      item('/engagement', 'Engagement & KYC', 'engagement_kyc', ['onboarding', 'aml', 'letter']),
      item('/litigation', 'Litigation Tracker', 'litigation_tracker', ['appeal', 'hearing', 'itat']),
    ],
  },
  {
    title: 'Delivery',
    items: [
      item('/reconciliation', 'GST Reconciliation', 'gst_reconciliation', ['gst', '2b', 'books']),
      item('/tds', 'TDS/TCS Reconciliation', 'tds_tcs_reconciliation', ['26as', 'ais', 'traces']),
      item('/msme', 'MSME 43B(h)', 'msme_43bh', ['udyam', '43bh']),
      item('/drawing-power', 'Drawing Power', 'drawing_power', ['bank', 'dp']),
      item('/certificates', 'CA Certificates', 'ca_certificates', ['certification', 'docx']),
      item('/secretarial', 'MCA Secretarial', 'mca_secretarial', ['mca', 'minutes']),
      item('/roc-xbrl', 'ROC / XBRL Tracker', 'roc_xbrl_tracker', ['xbrl', 'roc', 'filing']),
      item('/einvoice', 'E-Invoice / IRN', 'einvoice_irn', ['irn', 'einvoice']),
      item('/leases', 'Lease Intelligence', 'lease_intelligence', ['ind as 116', 'lease']),
    ],
  },
  {
    title: 'Assurance',
    items: [
      item('/audit', 'Audit Papers', 'audit_papers', ['working papers']),
      item('/observations', 'Query & Observations', 'query_observation_ledger', ['fieldwork', 'query']),
      item('/checklists', 'Statutory Checklists', 'statutory_checklist', ['caro', 'companies act']),
      item('/anomalies', 'Anomalies', 'anomalies', ['risk', 'fraud']),
      item('/invoices', 'Invoice Scanner', 'invoice_scanner', ['fraud scanner']),
      item('/notices', 'Notice Drafter', 'notice_drafter', ['draft', 'reply']),
      item('/logic-audit', 'Logic Audit (Layer 1)', 'logic_audit_layer1', ['rbi', 'pmla', 'z3', 'rules']),
      item('/causal-audit', 'Causal Audit (Layer 3)', 'causal_risk_layer3', ['root cause', 'forecast', 'rings']),
    ],
  },
  {
    title: 'Office',
    items: [
      item('/billing', 'Billing & Collections', 'billing_collections', ['fees', 'invoices', 'receipts']),
      item('/team', 'Team & Attendance', 'team_attendance', ['staff', 'capacity', 'hr']),
      item('/vault', 'DSC & Password Vault', 'dsc_password_vault', ['credentials', 'dsc', 'password']),
      item('/reports', 'Reports & Saved Views', 'reports_saved_views', ['analytics', 'saved views']),
      item('/diagnostics', 'Readiness Diagnostics', 'readiness_diagnostics', ['security', 'integrations']),
      item('/peer-review', 'Peer Review / QC', 'peer_review_qc', ['icai', 'qc']),
      item('/knowledge', 'SOP / Knowledge Base', 'sop_knowledge_base', ['wiki', 'sop']),
    ],
  },
  {
    title: 'Growth',
    items: [
      item('/benchmarking', 'Benchmarking', 'benchmarking', ['peers', 'analytics']),
      item('/rfp', 'RFP Bids', 'rfp_bids', ['proposal', 'bid']),
      item('/timesheets', 'Profitability Audit', 'profitability_audit', ['timesheet', 'margin']),
      item('/risk-scores', 'Client Risk Scoring', 'client_risk_scoring', ['risk', 'red flag']),
      item('/mis', 'Virtual CFO / MIS', 'virtual_cfo_mis', ['mis', 'dashboard', 'retainer']),
    ],
  },
];

export function navItemsForRole(role?: Role) {
  if (!role) return [];
  return NAV_GROUPS.flatMap(group =>
    group.items
      .filter(item => item.roles.includes(role))
      .map(item => ({ ...item, group: group.title })),
  );
}

export function navLabelForPath(pathname: string, role?: Role) {
  return navItemsForRole(role).find(item => item.href === pathname)?.label || 'CA Copilot';
}
