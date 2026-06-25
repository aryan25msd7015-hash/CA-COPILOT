'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams, useRouter } from 'next/navigation';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client, TransactionRecord } from '@/types';
import DataGrid from '@/components/shared/DataGrid';
import HealthBadge from '@/components/clients/HealthBadge';
import StatusBadge from '@/components/shared/StatusBadge';

interface HealthHistory {
  score: number;
  tier: string;
  components?: Record<string, number>;
  computed_at: string;
}

interface ClientSummary {
  metadata?: { compiled_at: string; ttl_seconds: number };
  health_matrix?: { current_score: number; status_indicator: string; friction_index: number };
  document_metrics?: { last_30_days: { pending: number; processing: number; ocr_complete: number; processed: number; failed: number } };
  deadline_metrics?: { open: number; overdue: number; due_in_48h: number };
  reconciliation_metrics?: { transaction_count: number; unreconciled_count: number; unreconciled_ratio: number };
  workload_vectors?: { open_tasks: number; current_month_hours: number; portal_open_requests: number; portal_contacts: number; tasks_by_service: Record<string, number> };
  billing_metrics?: { active_plans: number; unpaid_invoices: number };
  agent_context?: string;
  open_anomaly_count: number;
  upcoming_deadlines: { id: string; filing_name: string; period: string; deadline: string; status: string }[];
  recent_transactions: TransactionRecord[];
}

interface HealthAnalysis {
  current_score: number;
  current_tier: string;
  trend: { seven_day_delta?: number | null; moving_average_30: number; trajectory: string };
  events: {
    id: string;
    severity: string;
    delta: number;
    current_score: number;
    explanation: string;
    created_at: string;
  }[];
}

function ScoreSparkline({ history }: { history: HealthHistory[] }) {
  const values = [...history].reverse().map(item => item.score);
  if (values.length < 2) return <p className="text-xs text-gray-400">Run health scoring to build history.</p>;
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * 300;
    const y = 100 - value;
    return `${x},${y}`;
  }).join(' ');
  return <svg viewBox="0 0 300 100" className="h-24 w-full"><polyline points={points} fill="none" stroke="#2563eb" strokeWidth="3" /><line x1="0" y1="25" x2="300" y2="25" stroke="#d1fae5" /><line x1="0" y1="50" x2="300" y2="50" stroke="#fef3c7" /></svg>;
}

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const client = useQuery<Client>({ queryKey: ['client', id], queryFn: () => api.get(`/clients/${id}`).then(r => r.data) });
  const history = useQuery<HealthHistory[]>({ queryKey: ['client-health-history', id], queryFn: () => api.get(`/clients/${id}/health-history`).then(r => r.data), enabled: !!id });
  const summary = useQuery<ClientSummary>({ queryKey: ['client-summary', id], queryFn: () => api.get(`/clients/${id}/summary`).then(r => r.data), enabled: !!id });
  const analysis = useQuery<HealthAnalysis>({ queryKey: ['client-health-analysis', id], queryFn: () => api.get(`/health-scores/${id}/analysis`).then(r => r.data), enabled: !!id });
  const columns = useMemo<ColDef<TransactionRecord>[]>(() => [
    { field: 'invoice_no', headerName: 'Invoice' },
    { field: 'vendor_name', headerName: 'Vendor', minWidth: 180 },
    { field: 'amount', headerName: 'Amount', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'date', headerName: 'Date' },
    { field: 'match_status', headerName: 'Match', cellRenderer: (p: ICellRendererParams<TransactionRecord>) => <StatusBadge value={p.value} /> },
    { field: 'anomaly_score', headerName: 'Risk', valueFormatter: p => p.value == null ? '-' : `${Math.round(Number(p.value) * 100)}%` },
  ], []);

  if (client.isLoading) return <div className="text-sm text-gray-400">Loading...</div>;
  if (!client.data) return <div className="text-sm text-red-500">Client not found</div>;

  async function recomputeHealth() {
    await api.post(`/health-scores/recompute/${id}`);
    await Promise.all([client.refetch(), history.refetch(), summary.refetch(), analysis.refetch()]);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button onClick={() => router.back()} className="text-sm text-gray-500 hover:text-gray-900">Back</button>
        <h1 className="text-xl font-semibold text-gray-900">{client.data.name}</h1>
        <HealthBadge score={client.data.health_score} />
        <button onClick={recomputeHealth} className="ml-auto rounded-lg border px-3 py-2 text-sm text-blue-700">Recompute health</button>
      </div>

      <div className="grid gap-4 md:grid-cols-[220px_1fr]">
        <div className="flex items-center justify-center rounded-xl border bg-white p-5">
          <div className="flex h-36 w-36 items-center justify-center rounded-full" style={{ background: `conic-gradient(#2563eb ${client.data.health_score}%, #e5e7eb 0)` }}>
            <div className="flex h-28 w-28 flex-col items-center justify-center rounded-full bg-white"><strong className="text-3xl">{client.data.health_score}</strong><span className="text-xs text-gray-500">health score</span></div>
          </div>
        </div>
        <div className="rounded-xl border bg-white p-5"><h2 className="text-sm font-medium text-gray-700">30-day health trend</h2><ScoreSparkline history={history.data || []} /></div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[.7fr_1.3fr]">
        <div className="rounded-xl border bg-white p-4">
          <h2 className="text-sm font-medium text-gray-700">Health analytics</h2>
          <div className="mt-3 space-y-2 text-sm">
            <p className="flex justify-between"><span className="text-gray-500">Trajectory</span><span className="font-medium">{analysis.data?.trend.trajectory || 'stable'}</span></p>
            <p className="flex justify-between"><span className="text-gray-500">30-snapshot average</span><span className="font-medium">{analysis.data?.trend.moving_average_30 ?? client.data.health_score}</span></p>
            <p className="flex justify-between"><span className="text-gray-500">7-day delta</span><span className="font-medium">{analysis.data?.trend.seven_day_delta ?? '-'}</span></p>
          </div>
        </div>
        <div className="rounded-xl border bg-white p-4">
          <h2 className="text-sm font-medium text-gray-700">Score event timeline</h2>
          <div className="mt-3 space-y-3">
            {(analysis.data?.events || []).slice(0, 4).map(event => (
              <div key={event.id} className="rounded-lg bg-gray-50 p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-gray-900">{event.severity}</span>
                  <span className="text-xs text-gray-500">{new Date(event.created_at).toLocaleString('en-IN')}</span>
                </div>
                <p className="mt-1 text-gray-600">{event.explanation}</p>
              </div>
            ))}
            {!analysis.data?.events.length && <p className="text-xs text-gray-400">No score events yet.</p>}
          </div>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {[
          ['GSTIN', client.data.gstin || '-'],
          ['PAN', client.data.pan || '-'],
          ['TAN', client.data.tan || '-'],
          ['Industry', client.data.industry || '-'],
          ['WhatsApp', client.data.whatsapp_number || '-'],
          ['Email', client.data.email || '-'],
          ['Status', client.data.status || 'active'],
          ['Partition', client.data.client_partition || '-'],
          ['Open anomalies', String(summary.data?.open_anomaly_count || 0)],
        ].map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-sm font-medium">{value}</p></div>)}
      </div>

      <div className="grid gap-4 lg:grid-cols-4">
        {[
          ['Friction', `${summary.data?.health_matrix?.friction_index ?? 0}/100`],
          ['Due 48h', String(summary.data?.deadline_metrics?.due_in_48h ?? 0)],
          ['Failed docs', String(summary.data?.document_metrics?.last_30_days.failed ?? 0)],
          ['Unreconciled', `${summary.data?.reconciliation_metrics?.unreconciled_ratio ?? 0}%`],
          ['Open tasks', String(summary.data?.workload_vectors?.open_tasks ?? 0)],
          ['Month hours', String(summary.data?.workload_vectors?.current_month_hours ?? 0)],
          ['Portal asks', String(summary.data?.workload_vectors?.portal_open_requests ?? 0)],
          ['Unpaid invoices', String(summary.data?.billing_metrics?.unpaid_invoices ?? 0)],
        ].map(([label, value]) => (
          <div key={label} className="rounded-xl border bg-white p-4">
            <p className="text-xs text-gray-500">{label}</p>
            <p className="mt-1 text-lg font-semibold text-gray-900">{value}</p>
          </div>
        ))}
      </div>

      {summary.data?.agent_context && (
        <div className="rounded-xl border border-blue-100 bg-blue-50 p-4">
          <h2 className="text-sm font-medium text-blue-950">Agent context</h2>
          <p className="mt-2 text-sm leading-6 text-blue-900">{summary.data.agent_context}</p>
        </div>
      )}

      <div className="rounded-xl border bg-white p-4">
        <h2 className="mb-3 text-sm font-medium text-gray-700">Open deadlines</h2>
        <div className="grid gap-2 md:grid-cols-2">{(summary.data?.upcoming_deadlines || []).map(row => <div key={row.id} className="flex items-center justify-between rounded-lg bg-gray-50 p-3 text-sm"><div><p className="font-medium">{row.filing_name}</p><p className="text-xs text-gray-500">{row.period} · {new Date(row.deadline).toLocaleDateString('en-IN')}</p></div><StatusBadge value={row.status} /></div>)}</div>
        {!summary.data?.upcoming_deadlines.length && <p className="text-xs text-gray-400">No open deadlines.</p>}
      </div>

      <div><h2 className="mb-3 text-sm font-medium text-gray-700">Recent transactions</h2><DataGrid rows={summary.data?.recent_transactions || []} columns={columns} pagination={false} /></div>
    </div>
  );
}
