'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client, Organization } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface MetricComparison { client: number; median: number; p25: number; p75: number; delta_to_median: number; pct_delta_to_median: number; band: string; }
interface BenchmarkResult {
  client_name: string;
  industry: string;
  client_ratios: Record<string, number>;
  benchmarks?: Record<string, { median: number; p25: number; p75: number }>;
  metric_comparisons?: Record<string, MetricComparison>;
  peer_count: number;
  peer_source: string;
  minimum_peer_count: number;
}
interface BenchmarkStatus {
  consent: boolean;
  consent_at?: string;
  consent_source?: string;
  consent_note?: string;
  consent_by_user_id?: string;
  has_industry: boolean;
  can_compare: boolean;
  can_contribute_to_pool: boolean;
  plan?: string;
}
interface BenchmarkRow { metric: string; client: number; median?: number; p25?: number; p75?: number; delta?: number; pct_delta?: number; band?: string; }

export default function BenchmarkingPage() {
  const [clientId, setClientId] = useState('');
  const [message, setMessage] = useState('');
  const [consentSource, setConsentSource] = useState('internal_approval');
  const [consentNote, setConsentNote] = useState('');
  const org = useQuery<Organization>({ queryKey: ['organization'], queryFn: () => api.get('/organizations/me').then(r => r.data) });
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const selected = clients.data?.find(client => client.id === clientId);
  const status = useQuery<BenchmarkStatus>({ queryKey: ['benchmark-status', clientId], queryFn: () => api.get(`/benchmarking/${clientId}/status`).then(r => r.data), enabled: !!clientId });
  const result = useQuery<BenchmarkResult>({ queryKey: ['benchmark', clientId], queryFn: () => api.get(`/benchmarking/${clientId}`).then(r => r.data), enabled: !!clientId && org.data?.plan === 'premium' });
  const rows = useMemo<BenchmarkRow[]>(() => Object.entries(result.data?.client_ratios || {}).map(([metric, value]) => {
    const comparison = result.data?.metric_comparisons?.[metric];
    return {
      metric: metric.replaceAll('_', ' '),
      client: value,
      median: comparison?.median ?? result.data?.benchmarks?.[metric]?.median,
      p25: comparison?.p25 ?? result.data?.benchmarks?.[metric]?.p25,
      p75: comparison?.p75 ?? result.data?.benchmarks?.[metric]?.p75,
      delta: comparison?.delta_to_median,
      pct_delta: comparison?.pct_delta_to_median,
      band: comparison?.band,
    };
  }), [result.data]);
  const columns = useMemo<ColDef<BenchmarkRow>[]>(() => [
    { field: 'metric', headerName: 'Metric', minWidth: 180 },
    { field: 'client', headerName: 'Client' },
    { field: 'median', headerName: 'Industry median' },
    { field: 'p25', headerName: 'P25' },
    { field: 'p75', headerName: 'P75' },
    { field: 'delta', headerName: 'Delta' },
    { field: 'pct_delta', headerName: '% delta' },
    { field: 'band', headerName: 'Band', cellRenderer: (p: ICellRendererParams<BenchmarkRow>) => <StatusBadge value={String(p.value || 'insufficient')} /> },
  ], []);

  async function setConsent(consent: boolean) {
    if (!clientId) return;
    await api.post('/benchmarking/consent', { client_id: clientId, consent, source: consentSource, note: consentNote || undefined });
    await clients.refetch();
    await status.refetch();
    setMessage(consent ? 'Benchmark participation enabled.' : 'Benchmark participation disabled.');
  }

  return <div className="space-y-5">
    <PageHeader title="Industry Benchmarking" subtitle="Consent-based comparison against anonymized industry peers." />
    <div className="flex flex-wrap items-center gap-3 rounded-xl border bg-white p-4">
      <div className="min-w-64"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /></div>
      {selected && <select value={consentSource} onChange={event => setConsentSource(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
        <option value="internal_approval">Internal approval</option>
        <option value="client_email">Client email approval</option>
        <option value="engagement_letter">Engagement letter</option>
        <option value="partner_override">Partner override</option>
      </select>}
      {selected && <input value={consentNote} onChange={event => setConsentNote(event.target.value)} placeholder="Consent note" className="min-w-64 rounded-lg border px-3 py-2 text-sm" />}
      {selected && <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={Boolean(status.data?.consent ?? selected.benchmark_consent_at)} onChange={e => setConsent(e.target.checked)} />Include this client in anonymized peer benchmarks</label>}
      {message && <span className="text-xs text-green-700">{message}</span>}
    </div>
    {clientId && status.data && <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4 text-sm">
      <StatusBadge value={status.data.consent ? 'opted_in' : 'missing_consent'} />
      <span>Industry: {selected?.industry || '-'}</span>
      <span>Plan: {status.data.plan || '-'}</span>
      <span>Pool contribution: {status.data.can_contribute_to_pool ? 'enabled' : 'disabled'}</span>
      {status.data.consent_source && <span>Source: {status.data.consent_source.replaceAll('_', ' ')}</span>}
      {status.data.consent_note && <span>Note: {status.data.consent_note}</span>}
      {status.data.consent_at && <span>Consent: {new Date(status.data.consent_at).toLocaleString('en-IN')}</span>}
    </div>}
    {org.data && org.data.plan !== 'premium' ? <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">Viewing benchmark comparisons requires the premium plan. Consent controls remain available on every plan.</div> : <>
      {clientId && result.data && result.data.peer_count < 5 && <div className="rounded-xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-800">At least five consenting peer clients in the same industry are required. Current eligible peer count: {result.data.peer_count}.</div>}
      <DataGrid rows={rows} columns={columns} pagination={false} />
      {clientId && result.data && <p className="text-xs text-gray-500">Peer count: {result.data.peer_count} | Source: {result.data.peer_source.replaceAll('_', ' ')}</p>}
    </>}
  </div>;
}
