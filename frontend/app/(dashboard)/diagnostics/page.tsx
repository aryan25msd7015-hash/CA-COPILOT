'use client';

import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, ShieldCheck } from 'lucide-react';
import { api } from '@/lib/api';

type Integration = {
  status: 'ready' | 'degraded' | 'dev_fallback';
  configured: boolean;
  mode: string;
  [key: string]: unknown;
};

type IntegrationHealth = {
  checked_at: string;
  integrations: Record<string, Integration>;
  summary: Record<string, number>;
};

type SecurityDiagnostics = {
  checked_at: string;
  environment: string;
  security_headers: Record<string, boolean | string>;
  rate_limiter: { backend?: string; active_keys: number; active_hits: number };
  auth: Record<string, boolean | number>;
};

type AuditLogEntry = {
  id: string;
  action: string;
  ip_address?: string;
  payload: Record<string, unknown>;
  created_at?: string;
};

const statusClass = {
  ready: 'bg-emerald-50 text-emerald-700 ring-emerald-100',
  degraded: 'bg-amber-50 text-amber-700 ring-amber-100',
  dev_fallback: 'bg-slate-100 text-slate-600 ring-slate-200',
};

function StatusPill({ status }: { status: Integration['status'] }) {
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${statusClass[status]}`}>{status.replace('_', ' ')}</span>;
}

export default function DiagnosticsPage() {
  const integrations = useQuery<IntegrationHealth>({
    queryKey: ['integration-health'],
    queryFn: () => api.get('/integrations/health').then(res => res.data),
  });
  const security = useQuery<SecurityDiagnostics>({
    queryKey: ['security-diagnostics'],
    queryFn: () => api.get('/diagnostics/security').then(res => res.data),
  });
  const auditLog = useQuery<AuditLogEntry[]>({
    queryKey: ['audit-log'],
    queryFn: () => api.get('/diagnostics/audit-log', { params: { limit: 25 } }).then(res => res.data),
  });

  const integrationRows = Object.entries(integrations.data?.integrations || {});
  const securityControls = Object.entries(security.data?.auth || {});
  const headers = Object.entries(security.data?.security_headers || {});

  return (
    <div className="space-y-5">
      <div className="premium-panel rounded-2xl p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-sky-700">Market readiness</p>
            <h1 className="mt-1 text-2xl font-semibold text-slate-950">Diagnostics</h1>
            <p className="mt-1 text-sm text-slate-600">Runtime controls, provider modes, and production guardrails.</p>
          </div>
          <div className="flex items-center gap-2 rounded-2xl bg-white/80 px-3 py-2 text-sm font-medium text-slate-700 shadow-sm ring-1 ring-white">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            {security.data?.environment || 'checking'}
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="apple-surface rounded-2xl p-4">
          <p className="text-xs font-medium text-slate-500">Ready integrations</p>
          <p className="mt-1 text-2xl font-semibold text-slate-950">{integrations.data?.summary?.ready ?? 0}</p>
        </div>
        <div className="apple-surface rounded-2xl p-4">
          <p className="text-xs font-medium text-slate-500">Fallback integrations</p>
          <p className="mt-1 text-2xl font-semibold text-slate-950">{integrations.data?.summary?.dev_fallback ?? 0}</p>
        </div>
        <div className="apple-surface rounded-2xl p-4">
          <p className="text-xs font-medium text-slate-500">Rate limiter</p>
          <p className="mt-1 text-2xl font-semibold capitalize text-slate-950">{security.data?.rate_limiter?.backend || 'unknown'}</p>
        </div>
      </div>

      <section className="apple-surface rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Integrations</h2>
          {integrations.isLoading && <span className="text-xs text-slate-400">Checking...</span>}
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {integrationRows.map(([name, item]) => (
            <div key={name} className="rounded-xl border border-slate-200/80 bg-white/75 p-3 shadow-sm">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold capitalize text-slate-900">{name.replaceAll('_', ' ')}</p>
                <StatusPill status={item.status} />
              </div>
              <p className="mt-2 text-xs text-slate-500">{item.mode}</p>
              <div className="mt-3 flex items-center gap-2 text-xs text-slate-500">
                {item.configured ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <AlertTriangle className="h-4 w-4 text-amber-600" />}
                {item.configured ? 'Configured' : 'Setup required'}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="apple-surface rounded-2xl p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">Security Controls</h2>
          <div className="space-y-2">
            {securityControls.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between rounded-xl bg-white/75 px-3 py-2 text-sm">
                <span className="capitalize text-slate-600">{key.replaceAll('_', ' ')}</span>
                <span className="font-semibold text-slate-900">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="apple-surface rounded-2xl p-4">
          <h2 className="mb-3 text-sm font-semibold text-slate-900">HTTP Headers</h2>
          <div className="space-y-2">
            {headers.map(([key, value]) => (
              <div key={key} className="flex items-center justify-between rounded-xl bg-white/75 px-3 py-2 text-sm">
                <span className="capitalize text-slate-600">{key.replaceAll('_', ' ')}</span>
                <span className="font-semibold text-slate-900">{String(value)}</span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="apple-surface rounded-2xl p-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-900">Audit Log</h2>
          {auditLog.isLoading && <span className="text-xs text-slate-400">Loading...</span>}
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-white/70 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Time</th>
                <th className="px-3 py-2">Action</th>
                <th className="px-3 py-2">IP</th>
                <th className="px-3 py-2">Payload</th>
              </tr>
            </thead>
            <tbody>
              {(auditLog.data || []).map(row => (
                <tr key={row.id} className="border-t border-slate-100">
                  <td className="whitespace-nowrap px-3 py-2 text-slate-600">{row.created_at ? new Date(row.created_at).toLocaleString() : '-'}</td>
                  <td className="px-3 py-2 font-medium text-slate-900">{row.action}</td>
                  <td className="px-3 py-2 text-slate-600">{row.ip_address || '-'}</td>
                  <td className="max-w-xl truncate px-3 py-2 font-mono text-xs text-slate-500">{JSON.stringify(row.payload)}</td>
                </tr>
              ))}
              {!auditLog.data?.length && (
                <tr className="border-t border-slate-100">
                  <td colSpan={4} className="px-3 py-8 text-center text-slate-500">No audit events found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
