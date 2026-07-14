import { Role } from '@/types';

export interface NavItem {
  href: string;
  label: string;
  roles: Role[];
  keywords?: string[];
}

export interface NavGroup {
  title: string;
  items: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    title: 'Command',
    items: [
      { href: '/', label: 'Command Center', roles: ['partner', 'manager', 'article'], keywords: ['dashboard', 'home', 'overview'] },
      { href: '/autopilot', label: 'Exception Autopilot', roles: ['partner', 'manager'], keywords: ['review', 'exceptions', 'inbox'] },
      { href: '/query', label: 'Ask CA Copilot', roles: ['partner', 'manager', 'article'], keywords: ['search', 'nl query', 'ask'] },
    ],
  },
  {
    title: 'Practice',
    items: [
      { href: '/clients', label: 'Clients & CRM', roles: ['partner', 'manager', 'article'], keywords: ['crm', 'client master'] },
      { href: '/work', label: 'Work & Daybook', roles: ['partner', 'manager', 'article'], keywords: ['tasks', 'jobs', 'daybook'] },
      { href: '/documents', label: 'Document Vault', roles: ['partner', 'manager', 'article'], keywords: ['files', 'ocr', 'vault'] },
      { href: '/deadlines', label: 'Compliance Calendar', roles: ['partner', 'manager', 'article'], keywords: ['due dates', 'calendar'] },
      { href: '/whatsapp', label: 'WhatsApp Desk', roles: ['partner', 'manager'], keywords: ['messages', 'reminders'] },
      { href: '/portal', label: 'Client Portal', roles: ['partner', 'manager'], keywords: ['requests', 'approvals'] },
      { href: '/imports', label: 'Guided Imports', roles: ['partner', 'manager', 'article'], keywords: ['tally', 'excel', 'mapping'] },
    ],
  },
  {
    title: 'Delivery',
    items: [
      { href: '/reconciliation', label: 'GST Reconciliation', roles: ['partner', 'manager', 'article'], keywords: ['gst', '2b', 'books'] },
      { href: '/msme', label: 'MSME 43B(h)', roles: ['partner', 'manager'], keywords: ['udyam', '43bh'] },
      { href: '/drawing-power', label: 'Drawing Power', roles: ['partner', 'manager'], keywords: ['bank', 'dp'] },
      { href: '/certificates', label: 'CA Certificates', roles: ['partner', 'manager'], keywords: ['certification', 'docx'] },
      { href: '/secretarial', label: 'MCA Secretarial', roles: ['partner', 'manager'], keywords: ['mca', 'minutes'] },
      { href: '/leases', label: 'Lease Intelligence', roles: ['partner', 'manager'], keywords: ['ind as 116', 'lease'] },
    ],
  },
  {
    title: 'Assurance',
    items: [
      { href: '/audit', label: 'Audit Papers', roles: ['partner', 'manager'], keywords: ['working papers'] },
      { href: '/anomalies', label: 'Anomalies', roles: ['partner', 'manager'], keywords: ['risk', 'fraud'] },
      { href: '/invoices', label: 'Invoice Scanner', roles: ['partner', 'manager'], keywords: ['fraud scanner'] },
      { href: '/notices', label: 'Notice Drafter', roles: ['partner', 'manager'], keywords: ['draft', 'reply'] },
    ],
  },
  {
    title: 'Office',
    items: [
      { href: '/billing', label: 'Billing & Collections', roles: ['partner', 'manager'], keywords: ['fees', 'invoices', 'receipts'] },
      { href: '/team', label: 'Team & Attendance', roles: ['partner', 'manager'], keywords: ['staff', 'capacity', 'hr'] },
      { href: '/vault', label: 'DSC & Password Vault', roles: ['partner', 'manager'], keywords: ['credentials', 'dsc', 'password'] },
      { href: '/reports', label: 'Reports & Saved Views', roles: ['partner', 'manager', 'article'], keywords: ['analytics', 'saved views'] },
      { href: '/diagnostics', label: 'Readiness Diagnostics', roles: ['partner', 'manager'], keywords: ['security', 'integrations', 'health'] },
      { href: '/email-preview', label: 'Email Templates', roles: ['partner', 'manager'], keywords: ['email', 'resend', 'templates', 'preview'] },
    ],
  },
  {
    title: 'Growth',
    items: [
      { href: '/benchmarking', label: 'Benchmarking', roles: ['partner'], keywords: ['peers', 'analytics'] },
      { href: '/rfp', label: 'RFP Bids', roles: ['partner'], keywords: ['proposal', 'bid'] },
      { href: '/timesheets', label: 'Profitability Audit', roles: ['partner'], keywords: ['timesheet', 'margin'] },
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
