'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { downloadFromApi } from '@/lib/download';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface Lease { id: string; name: string; extracted_data: Record<string, unknown>; schedule: Record<string, number>[]; summary: { initial_lease_liability?: number; initial_rou_asset?: number; months: number; total_payments: number; total_interest: number; monthly_rent: number; ibr_pct: number; commencement_date?: string; rent_free_months: number; ending_liability: number }; ibr_assumed: boolean; verified: boolean; review_flags: string[]; review_ready: boolean; }
interface Overview { total: number; verified: number; pending_review: number; ibr_assumed: number; total_liability: number; total_rou_asset: number; total_payments: number; total_interest: number; average_term_months: number; }

export default function LeasesPage() {
  const [clientId, setClientId] = useState('');
  const [name, setName] = useState('');
  const [sourceText, setSourceText] = useState('');
  const [dataJson, setDataJson] = useState('{"lease_term_months":36,"base_rent_monthly":100000,"rent_free_period_months":2,"incremental_borrowing_rate_pct":9,"escalation_clauses":[{"effective_from_month":25,"rate_pct":5,"type":"fixed"}]}');
  const [selected, setSelected] = useState<Lease | null>(null);
  const [editingId, setEditingId] = useState('');
  const [message, setMessage] = useState('');
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const leases = useQuery<Lease[]>({ queryKey: ['leases', clientId], queryFn: () => api.get(`/leases?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  const overview = useQuery<Overview>({ queryKey: ['lease-overview', clientId], queryFn: () => api.get(`/leases/overview?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  async function calculate() {
    const response = editingId
      ? await api.patch(`/leases/${editingId}`, { data: JSON.parse(dataJson), verified: false })
      : await api.post('/leases', { client_id: clientId, name, source_text: sourceText, data: JSON.parse(dataJson) });
    setSelected(response.data);
    setMessage(`Lease schedule calculated for ${response.data.summary.months} months; liability INR ${Number(response.data.summary.initial_lease_liability || 0).toLocaleString('en-IN')}.`);
    await Promise.all([leases.refetch(), overview.refetch()]);
  }
  function review(row: Lease) {
    setSelected(row);
    setEditingId(row.id);
    setName(row.name);
    setDataJson(JSON.stringify(row.extracted_data, null, 2));
  }
  function reset() {
    setEditingId('');
    setSelected(null);
    setName('');
  }
  async function verify(row: Lease) { const response = await api.patch(`/leases/${row.id}`, { verified: true }); setMessage(`${response.data.name} marked CA verified.`); await Promise.all([leases.refetch(), overview.refetch()]); }
  const columns: ColDef<Lease>[] = [
    { field: 'name', headerName: 'Lease', minWidth: 190 }, { headerName: 'Term', valueGetter: p => `${p.data?.summary.months || 0} months` },
    { headerName: 'Initial liability', valueGetter: p => p.data?.summary.initial_lease_liability, valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { headerName: 'Total interest', valueGetter: p => p.data?.summary.total_interest, valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'ibr_assumed', headerName: 'IBR source', cellRenderer: (p: ICellRendererParams<Lease>) => <StatusBadge value={p.value ? 'review_required' : 'verified'} /> },
    { field: 'verified', headerName: 'CA verified', cellRenderer: (p: ICellRendererParams<Lease>) => <StatusBadge value={p.value ? 'verified' : 'pending'} /> },
    { headerName: 'Flags', valueGetter: p => p.data?.review_flags?.length || 0 },
    { headerName: 'Actions', minWidth: 190, sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<Lease>) => <div className="flex h-full items-center gap-3"><button onClick={() => p.data && review(p.data)} className="text-xs text-blue-700">Review values</button>{!p.data?.verified && <button onClick={() => p.data && verify(p.data)} className="text-xs text-green-700">Verify</button>}<button onClick={() => p.data && downloadFromApi(`/leases/${p.data.id}/export`, `lease-schedule-${p.data.id}.xlsx`)} className="text-xs text-purple-700">Excel</button></div> },
  ];
  const metrics = [
    ['Leases', overview.data?.total || 0],
    ['Verified', overview.data?.verified || 0],
    ['Pending review', overview.data?.pending_review || 0],
    ['IBR assumed', overview.data?.ibr_assumed || 0],
    ['Lease liability', `INR ${Number(overview.data?.total_liability || 0).toLocaleString('en-IN')}`],
    ['ROU asset', `INR ${Number(overview.data?.total_rou_asset || 0).toLocaleString('en-IN')}`],
    ['Total payments', `INR ${Number(overview.data?.total_payments || 0).toLocaleString('en-IN')}`],
    ['Avg term', `${Number(overview.data?.average_term_months || 0).toFixed(1)} months`],
  ];
  return <div className="space-y-5">
    <PageHeader title="Lease Intelligence" subtitle="Extract lease terms, review IBR assumptions, and calculate Ind AS 116 / IFRS 16 schedules." />
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><input value={name} onChange={e => setName(e.target.value)} placeholder="Lease name" className="rounded-lg border px-3 py-2 text-sm" /><button disabled={!clientId || !name} onClick={calculate} className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">{editingId ? 'Save review & recalculate' : 'Calculate schedule'}</button>{editingId && <button onClick={reset} className="rounded-lg border px-3 py-2 text-sm">New lease</button>}</div>
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    <div className="grid gap-4 lg:grid-cols-2"><label className="text-sm font-medium">Lease agreement text<textarea value={sourceText} onChange={e => setSourceText(e.target.value)} rows={10} placeholder="Commencement date: 2026-04-01. Lease term: 36 months. Monthly rent: INR 100,000..." className="mt-1 w-full rounded-xl border p-3 text-sm" /></label><label className="text-sm font-medium">Extracted values / manual overrides<textarea value={dataJson} onChange={e => setDataJson(e.target.value)} rows={10} className="mt-1 w-full rounded-xl border p-3 font-mono text-xs" /></label></div>
    {message && <p className="text-sm text-green-700">{message}</p>}
    {selected && <div className="rounded-xl border bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-sm font-semibold">Review extracted values: {selected.name}</h2><div className="flex gap-2">{selected.review_flags.map(flag => <StatusBadge key={flag} value={flag === 'ibr_assumed' ? 'review_required' : 'risk_medium'} />)}</div></div><div className="mt-3 grid gap-3 sm:grid-cols-4">{[['Liability', selected.summary.initial_lease_liability], ['ROU asset', selected.summary.initial_rou_asset], ['Interest', selected.summary.total_interest], ['Ending liability', selected.summary.ending_liability]].map(([label, value]) => <div key={label} className="rounded-lg border p-3"><p className="text-xs text-gray-500">{label}</p><p className="text-sm font-semibold">INR {Number(value || 0).toLocaleString('en-IN')}</p></div>)}</div><pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-xs">{JSON.stringify(selected.extracted_data, null, 2)}</pre></div>}
    <DataGrid rows={leases.data || []} columns={columns} />
  </div>;
}
