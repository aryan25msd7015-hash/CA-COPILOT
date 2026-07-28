import { Role } from '@/types';

export type DemoTier = Role | 'client';

export interface DemoAccount {
  tier: DemoTier;
  label: string;
  email: string;
  password: string;
  workspace: string;
  auth: 'firm' | 'portal';
  summary: string;
}

export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    tier: 'partner',
    label: 'Firm Head / Partner',
    email: 'partner@cacopilot.example.com',
    password: 'PartnerDemo123',
    workspace: '/workspaces/partner',
    auth: 'firm',
    summary: 'Firm-wide control, CA assignment, growth & vault access.',
  },
  {
    tier: 'manager',
    label: 'CA (Manager)',
    email: 'ca@cacopilot.example.com',
    password: 'CADemo123',
    workspace: '/workspaces/ca',
    auth: 'firm',
    summary: 'Assigned clients, reviews, approvals and delivery sign-off.',
  },
  {
    tier: 'article',
    label: 'Intern / Staff',
    email: 'staff@cacopilot.example.com',
    password: 'StaffDemo123',
    workspace: '/workspaces/staff',
    auth: 'firm',
    summary: 'Execution queue: drafts, uploads, reconciliations and fieldwork.',
  },
  {
    tier: 'client',
    label: 'Client',
    email: 'client@apex.example.com',
    password: 'ClientDemo123',
    workspace: '/client-portal',
    auth: 'portal',
    summary: 'Own documents, deadlines, invoices and portal requests only.',
  },
];

export const ROLE_HOME: Record<Role, string> = {
  partner: '/workspaces/partner',
  manager: '/workspaces/ca',
  article: '/workspaces/staff',
};

export function homeForRole(role?: Role | string | null): string {
  if (!role) return '/login';
  return ROLE_HOME[role as Role] || '/';
}
