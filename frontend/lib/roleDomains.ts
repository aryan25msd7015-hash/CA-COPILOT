import { Role } from '@/types';
import { DEMO_ACCOUNTS, DemoAccount, ROLE_HOME } from '@/lib/demoAccounts';

/** Product desk bound to one public hostname. */
export type AppDesk = 'partner' | 'manager' | 'article' | 'client' | 'hub';

export interface DeskConfig {
  desk: AppDesk;
  role: Role | 'client';
  label: string;
  home: string;
  /** Path prefixes allowed on this desk domain (besides Next internals). */
  allowedPrefixes: string[];
  accent: 'partner' | 'ca' | 'staff' | 'client';
  features: string[];
}

export const DESK_CONFIG: Record<Exclude<AppDesk, 'hub'>, DeskConfig> = {
  partner: {
    desk: 'partner',
    role: 'partner',
    label: 'Firm Head / Partner',
    home: ROLE_HOME.partner,
    accent: 'partner',
    features: [
      'workspace_partner',
      'clients_crm',
      'team_attendance',
      'billing_collections',
      'benchmarking',
      'profitability_audit',
      'dsc_password_vault',
      'peer_review_qc',
      'ai_audit_orchestrator',
    ],
    allowedPrefixes: [
      '/login',
      '/register',
      '/auth',
      '/workspaces/partner',
      '/clients',
      '/team',
      '/billing',
      '/benchmarking',
      '/timesheets',
      '/vault',
      '/peer-review',
      '/audit-orchestrator',
    ],
  },
  manager: {
    desk: 'manager',
    role: 'manager',
    label: 'CA (Manager)',
    home: ROLE_HOME.manager,
    accent: 'ca',
    features: [
      'workspace_ca',
      'clients_crm',
      'audit_papers',
      'anomalies',
      'notice_drafter',
      'gst_reconciliation',
      'query_observation_ledger',
      'exception_autopilot',
      'causal_risk_layer3',
      'logic_audit_layer1',
    ],
    allowedPrefixes: [
      '/login',
      '/register',
      '/auth',
      '/workspaces/ca',
      '/clients',
      '/audit',
      '/anomalies',
      '/notices',
      '/reconciliation',
      '/observations',
      '/autopilot',
      '/causal-audit',
      '/logic-audit',
    ],
  },
  article: {
    desk: 'article',
    role: 'article',
    label: 'Intern / Staff',
    home: ROLE_HOME.article,
    accent: 'staff',
    features: [
      'workspace_staff',
      'work_daybook',
      'document_vault',
      'compliance_calendar',
      'gst_reconciliation',
      'guided_imports',
      'query_observation_ledger',
      'statutory_checklist',
      'ask_ca_copilot',
    ],
    allowedPrefixes: [
      '/login',
      '/register',
      '/auth',
      '/workspaces/staff',
      '/work',
      '/documents',
      '/deadlines',
      '/reconciliation',
      '/imports',
      '/observations',
      '/checklists',
      '/query',
    ],
  },
  client: {
    desk: 'client',
    role: 'client',
    label: 'Client',
    home: '/client-portal',
    accent: 'client',
    features: [],
    allowedPrefixes: ['/client-portal', '/login'],
  },
};

const DESK_COOKIE = 'ca_app_desk';
const DESK_HEADER = 'x-ca-app-desk';

export { DESK_COOKIE, DESK_HEADER };

/** Parse `host=desk,host2=desk2` or `host:desk;host2:desk2`. */
export function parseRoleDomainMap(raw: string | undefined | null): Record<string, AppDesk> {
  if (!raw?.trim()) return {};
  const out: Record<string, AppDesk> = {};
  for (const part of raw.split(/[,;]/)) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const sep = trimmed.includes('=') ? '=' : trimmed.includes(':') ? ':' : null;
    if (!sep) continue;
    const idx = trimmed.indexOf(sep);
    const host = normalizeHost(trimmed.slice(0, idx));
    const desk = trimmed.slice(idx + 1).trim() as AppDesk;
    if (host && isAppDesk(desk) && desk !== 'hub') {
      out[host] = desk;
    }
  }
  return out;
}

/** Parse `partner=https://...,manager=https://...`. */
export function parseRoleDomainUrls(raw: string | undefined | null): Partial<Record<Exclude<AppDesk, 'hub'>, string>> {
  if (!raw?.trim()) return {};
  const out: Partial<Record<Exclude<AppDesk, 'hub'>, string>> = {};
  for (const part of raw.split(/[,;]/)) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const sep = trimmed.includes('=') ? '=' : trimmed.includes(':') ? ':' : null;
    if (!sep) continue;
    const idx = trimmed.indexOf(sep);
    const desk = trimmed.slice(0, idx).trim() as AppDesk;
    const url = trimmed.slice(idx + 1).trim().replace(/\/$/, '');
    if (isAppDesk(desk) && desk !== 'hub' && url.startsWith('http')) {
      out[desk] = url;
    }
  }
  return out;
}

export function isAppDesk(value: string): value is AppDesk {
  return value === 'partner' || value === 'manager' || value === 'article' || value === 'client' || value === 'hub';
}

export function normalizeHost(host: string): string {
  return host.trim().toLowerCase().replace(/:\d+$/, '');
}

export function getServerDomainMap(): Record<string, AppDesk> {
  return parseRoleDomainMap(
    process.env.ROLE_DOMAIN_MAP || process.env.NEXT_PUBLIC_ROLE_DOMAIN_MAP || '',
  );
}

export function getClientDomainUrls(): Partial<Record<Exclude<AppDesk, 'hub'>, string>> {
  return parseRoleDomainUrls(
    process.env.NEXT_PUBLIC_ROLE_DOMAIN_URLS || process.env.ROLE_DOMAIN_URLS || '',
  );
}

export function deskFromHost(host: string | null | undefined): AppDesk {
  const forced = (process.env.NEXT_PUBLIC_APP_ROLE || process.env.APP_ROLE || '').trim();
  if (isAppDesk(forced) && forced !== 'hub') return forced;
  if (!host) return 'hub';
  const map = getServerDomainMap();
  return map[normalizeHost(host)] || 'hub';
}

export function deskFromCookie(cookieHeader: string | null | undefined): AppDesk | null {
  if (!cookieHeader) return null;
  const match = cookieHeader.match(/(?:^|;\s*)ca_app_desk=([^;]+)/);
  const value = match?.[1]?.trim();
  return value && isAppDesk(value) ? value : null;
}

export function getBrowserDesk(): AppDesk {
  if (typeof window === 'undefined') {
    const forced = (process.env.NEXT_PUBLIC_APP_ROLE || '').trim();
    return isAppDesk(forced) ? forced : 'hub';
  }
  const fromHost = deskFromHost(window.location.host);
  if (fromHost !== 'hub') return fromHost;
  const match = document.cookie.match(/(?:^|;\s*)ca_app_desk=([^;]+)/);
  const value = match?.[1]?.trim();
  if (value && isAppDesk(value)) return value;
  const forced = (process.env.NEXT_PUBLIC_APP_ROLE || '').trim();
  return isAppDesk(forced) ? forced : 'hub';
}

export function isPathAllowedForDesk(desk: AppDesk, pathname: string): boolean {
  if (desk === 'hub') return true;
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/favicon') ||
    pathname === '/robots.txt' ||
    pathname.startsWith('/api')
  ) {
    return true;
  }
  const config = DESK_CONFIG[desk];
  return config.allowedPrefixes.some(
    prefix => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function deskHome(desk: AppDesk): string {
  if (desk === 'hub') return '/login';
  return DESK_CONFIG[desk].home;
}

export function demoAccountForDesk(desk: AppDesk): DemoAccount | undefined {
  if (desk === 'hub') return undefined;
  return DEMO_ACCOUNTS.find(account => account.tier === desk);
}

export function absoluteHomeForRole(role?: Role | string | null): string | null {
  if (!role) return null;
  const urls = getClientDomainUrls();
  if (role === 'partner' && urls.partner) return `${urls.partner}${ROLE_HOME.partner}`;
  if (role === 'manager' && urls.manager) return `${urls.manager}${ROLE_HOME.manager}`;
  if (role === 'article' && urls.article) return `${urls.article}${ROLE_HOME.article}`;
  if (role === 'client' && urls.client) return `${urls.client}/client-portal`;
  return null;
}

export function deskMatchesUserRole(desk: AppDesk, role?: Role | string | null): boolean {
  if (desk === 'hub' || !role) return true;
  if (desk === 'client') return role === 'client';
  return desk === role;
}
