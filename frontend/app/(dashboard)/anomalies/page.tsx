'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client } from '@/types';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface FlagTransaction {
  invoice_no?: string;
  vendor_name?: string;
  vendor_gstin?: string;
  amount?: number;
  tax_amount?: number;
  date?: string;
  match_status?: string;
  audit_risk_score?: number;
  audit_risk_prob?: number;
}
interface Driver {
  feature?: string;
  contribution?: number;
  direction?: string;
}
interface Flag {
  id: string;
  flag_type: string;
  client_id: string;
  client_name?: string;
  risk_score: number;
  details?: Record<string, unknown>;
  drivers?: Driver[];
  layers?: Record<string, number>;
  reviewed: boolean;
  review_status: string;
  review_note?: string;
  reviewed_at?: string;
  transaction?: FlagTransaction;
}
interface SummaryBucket { count: number; max_risk: number; }
interface Summary {
  total: number;
  open: SummaryBucket;
  confirmed: SummaryBucket;
  false_positive: SummaryBucket;
  needs_followup: SummaryBucket;
}
interface PriorityItem {
  id: string;
  flag_type?: string;
  priority_score?: number;
  bandit_arm_label?: string;
  risk_prob?: number;
  impact_amount?: number;
  drivers?: Driver[];
}

const STATUSES = ['open', 'confirmed', 'needs_followup', 'false_positive'];

function formatDrivers(drivers?: Driver[]) {
  if (!drivers?.length) return '-';
  return drivers.slice(0, 3).map(d => `${d.feature}:${Number(d.contribution || 0).toFixed(2)}`).join(' · ');
}

export default function AnomaliesPage() {
  const [type, setType] = useState('');
  const [status, setStatus] = useState('open');
  const [clientId, setClientId] = useState('');
  const [minRisk, setMinRisk] = useState('0');
  const [search, setSearch] = useState('');
  const [noteById, setNoteById] = useState<Record<string, string>>({});
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const summary = useQuery<Summary>({ queryKey: ['anomaly-summary'], queryFn: () => api.get('/anomalies/summary').then(r => r.data) });
  const haeStatus = useQuery({ queryKey: ['hae-status'], queryFn: () => api.get('/hybrid-audit/status').then(r => r.data) });
  const prioritized = useQuery<{ count: number; items: PriorityItem[] }>({
    queryKey: ['hae-prioritize', clientId],
    queryFn: () => api.post('/hybrid-audit/prioritize', { client_id: clientId || undefined, limit: 8 }).then(r => r.data),
  });
  const query = useQuery<Flag[]>({
    queryKey: ['anomalies', type, status, clientId, minRisk, search],
    queryFn: () => api.get('/anomalies', {
      params: {
        ...(type ? { flag_type: type } : {}),
        ...(status ? { review_status: status } : {}),
        ...(clientId ? { client_id: clientId } : {}),
        ...(Number(minRisk) > 0 ? { min_risk: Number(minRisk) } : {}),
        ...(search.trim() ? { q: search.trim() } : {}),
        limit: 1000,
      },
    }).then(r => r.data),
  });
  const allTypes = useQuery<Flag[]>({ queryKey: ['anomaly-types'], queryFn: () => api.get('/anomalies', { params: { limit: 5000 } }).then(r => r.data) });
  const types = useMemo(() => Array.from(new Set((allTypes.data || []).map(flag => flag.flag_type))).sort(), [allTypes.data]);

  const review = useCallback(async (flag: Flag, reviewStatus: string) => {
    await api.patch(`/anomalies/${flag.id}/review`, {
      review_status: reviewStatus,
      note: noteById[flag.id] || undefined,
    });
    await Promise.all([query.refetch(), summary.refetch(), allTypes.refetch(), prioritized.refetch()]);
  }, [allTypes, noteById, prioritized, query, summary]);

  const runScore = useCallback(async () => {
    if (!clientId) return;
    await api.post('/hybrid-audit/score', { client_id: clientId, async_run: true });
    await Promise.all([query.refetch(), summary.refetch(), haeStatus.refetch()]);
  }, [clientId, haeStatus, query, summary]);

  const columns = useMemo<ColDef<Flag>[]>(() => [
    { field: 'flag_type', headerName: 'Type', minWidth: 150 },
    { field: 'client_name', headerName: 'Client', minWidth: 190, valueFormatter: p => String(p.value || p.data?.client_id || '-') },
    {
      field: 'risk_score',
      headerName: 'Risk',
      minWidth: 110,
      valueFormatter: p => `${Math.round(Number(p.value || 0) * 100)}%`,
      cellClassRules: { 'text-red-700 font-semibold': p => Number(p.value || 0) >= 0.7 },
    },
    {
      headerName: 'HAE Drivers',
      minWidth: 220,
      valueGetter: p => formatDrivers(p.data?.drivers),
    },
    {
      field: 'review_status',
      headerName: 'Review',
      minWidth: 140,
      cellRenderer: (p: ICellRendererParams<Flag>) => <StatusBadge value={p.data?.review_status} />,
    },
    { headerName: 'Vendor', minWidth: 180, valueGetter: p => p.data?.transaction?.vendor_name || '-' },
    { headerName: 'Invoice', minWidth: 140, valueGetter: p => p.data?.transaction?.invoice_no || '-' },
    { headerName: 'Amount', minWidth: 120, valueGetter: p => p.data?.transaction?.amount ?? '-', valueFormatter: p => typeof p.value === 'number' ? p.value.toLocaleString('en-IN') : String(p.value) },
    { field: 'details', headerName: 'Details', minWidth: 220, valueFormatter: p => JSON.stringify(p.value || {}) },
    {
      headerName: 'Decision',
      minWidth: 430,
      sortable: false,
      filter: false,
      cellRenderer: (p: ICellRendererParams<Flag>) => <div className="flex h-full items-center gap-2">
        <input
          value={p.data ? noteById[p.data.id] || '' : ''}
          onChange={event => p.data && setNoteById(prev => ({ ...prev, [p.data!.id]: event.target.value }))}
          placeholder="Review note"
          className="w-36 rounded border px-2 py-1 text-xs"
        />
        {p.data && <button onClick={() => review(p.data!, 'confirmed')} className="text-xs text-red-700">Confirm</button>}
        {p.data && <button onClick={() => review(p.data!, 'needs_followup')} className="text-xs text-amber-700">Follow up</button>}
        {p.data && <button onClick={() => review(p.data!, 'false_positive')} className="text-xs text-green-700">False positive</button>}
        {p.data && p.data.review_status !== 'open' && <button onClick={() => review(p.data!, 'open')} className="text-xs text-gray-600">Reopen</button>}
      </div>,
    },
  ], [noteById, review]);

  return <div className="space-y-5">
    <PageHeader title="Anomaly Dashboard" subtitle="HAE-4 hybrid engine: rules, Isolation Forest/LOF, LightGBM, temporal + graph scores, LinUCB priority." />
    <div className="grid gap-3 md:grid-cols-4">
      {STATUSES.map(item => <button key={item} onClick={() => setStatus(item)} className={`rounded-xl border p-4 text-left ${status === item ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-900'}`}>
        <p className="text-xs opacity-70">{item.replaceAll('_', ' ')}</p>
        <p className="mt-1 text-2xl font-semibold">{summary.data?.[item as keyof Summary] && typeof summary.data[item as keyof Summary] === 'object' ? (summary.data[item as keyof Summary] as SummaryBucket).count : 0}</p>
      </button>)}
    </div>
    <div className="rounded-xl border bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-xs uppercase tracking-wide text-gray-500">HAE priority queue</p>
          <p className="text-sm text-gray-700">LinUCB ranks open flags for reviewer attention. Engine: {haeStatus.data?.engine || 'HAE-4'} · scored txns: {haeStatus.data?.scored_transactions ?? '—'}</p>
        </div>
        <button disabled={!clientId} onClick={runScore} className="rounded-lg bg-blue-600 px-3 py-2 text-xs font-medium text-white disabled:opacity-50">Run HAE score</button>
      </div>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        {(prioritized.data?.items || []).slice(0, 6).map(item => (
          <div key={item.id} className="rounded-lg border px-3 py-2 text-xs">
            <div className="flex justify-between gap-2">
              <span className="font-medium">{item.flag_type || 'flag'}</span>
              <span>{Math.round(Number(item.priority_score || 0) * 100)}% priority · {item.bandit_arm_label}</span>
            </div>
            <p className="mt-1 text-gray-600">{formatDrivers(item.drivers)}</p>
          </div>
        ))}
        {!prioritized.data?.items?.length && <p className="text-xs text-gray-500">No open flags to prioritize yet.</p>}
      </div>
    </div>
    <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-3">
      <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search client, vendor, invoice, type" className="min-w-64 rounded-lg border px-3 py-2 text-sm" />
      <select value={clientId} onChange={event => setClientId(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
        <option value="">All clients</option>
        {(clients.data || []).map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
      </select>
      <select value={type} onChange={event => setType(event.target.value)} className="rounded-lg border px-3 py-2 text-sm"><option value="">All types</option>{types.map(item => <option key={item}>{item}</option>)}</select>
      <select value={minRisk} onChange={event => setMinRisk(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
        <option value="0">All risk</option>
        <option value="0.5">50%+</option>
        <option value="0.7">70%+</option>
        <option value="0.9">90%+</option>
      </select>
    </div>
    <DataGrid rows={query.data || []} columns={columns} pageSize={20} />
  </div>;
}
