'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client } from '@/types';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';
import ClientSelect from '@/components/shared/ClientSelect';

interface BasicDeadline {
  id: string; client_id: string; filing_type: string; filing_name: string;
  period: string; deadline: string; status: string; filed_at?: string; doc_required?: string;
  calendar_item_id?: string;
  risk_score: number; risk_tier: string; days_until_due: number; data_received: boolean;
  late_count_last_12m: number; has_open_notice: boolean;
}

interface OverviewRow {
  filing_type: string; filing_name: string; period: string; deadline: string;
  total_pending: number; high_risk_count: number; data_missing: number;
  chronic_late: number; has_notice: number; max_risk: number; priority: string;
  reminder_candidates: number; reminders_sent_total: number; days_until_deadline: number;
}
interface DetailRow {
  id: string; client_name: string; gstin?: string; health_score: number;
  risk_score: number; data_received: boolean; data_source?: string;
  late_count_last_12m: number; has_open_notice: boolean; reminders_sent: number; status: string;
  reminder_eligible: boolean; last_reminder_at?: string;
}

export default function DeadlinesPage() {
  const [selected, setSelected] = useState<OverviewRow | null>(null);
  const [message, setMessage] = useState('');
  const [clientId, setClientId] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [form, setForm] = useState({
    client_id: '',
    filing_type: 'GSTR3B',
    filing_name: 'GSTR-3B Monthly Return',
    period: new Date().toISOString().slice(0, 7),
    deadline: new Date().toISOString().slice(0, 10),
    doc_required: 'purchase_register',
  });
  const overview = useQuery<OverviewRow[]>({ queryKey: ['advanced-calendar'], queryFn: () => api.get('/calendar/overview?days_ahead=365').then(r => r.data) });
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const deadlines = useQuery<BasicDeadline[]>({
    queryKey: ['deadlines-basic', clientId, statusFilter],
    queryFn: () => api.get('/deadlines', { params: { client_id: clientId || undefined, status: statusFilter || undefined, limit: 5000 } }).then(r => r.data),
  });
  const clientDeadlineView = useQuery<BasicDeadline[]>({
    queryKey: ['deadlines-client-view', clientId, statusFilter],
    queryFn: () => api.get(`/deadlines/client/${clientId}`, { params: { status: statusFilter || undefined, limit: 5000 } }).then(r => r.data),
    enabled: !!clientId,
  });
  const detail = useQuery<DetailRow[]>({
    queryKey: ['calendar-detail', selected?.filing_type, selected?.period],
    queryFn: () => api.get(`/calendar/${selected!.filing_type}/${selected!.period}/clients`).then(r => r.data),
    enabled: !!selected,
  });

  async function seedAll() {
    await Promise.all((clients.data || []).map(client => api.post(`/calendar/seed/${client.id}`)));
    await overview.refetch();
    setMessage('Applicable filings seeded for every client.');
  }
  async function score() {
    const response = await api.post('/calendar/score');
    await Promise.all([overview.refetch(), detail.refetch()]);
    setMessage(`${response.data.scored} rows rescored: ${response.data.high_risk} high-risk, ${response.data.missing_data} missing data.`);
  }
  async function remind(row: OverviewRow) {
    const response = await api.post(`/calendar/${row.filing_type}/${row.period}/bulk-remind`);
    await detail.refetch();
    await overview.refetch();
    setMessage(`${response.data.reminders_sent}/${response.data.eligible} reminders queued; ${response.data.blocked_no_consent} blocked by consent, ${response.data.provider_skipped} provider skipped.`);
  }
  async function update(id: string, values: Record<string, unknown>) {
    await api.patch(`/calendar/items/${id}`, values);
    await Promise.all([overview.refetch(), detail.refetch()]);
  }
  async function createDeadline() {
    await api.post('/deadlines', { ...form, client_id: form.client_id || clientId });
    await deadlines.refetch();
    await overview.refetch();
    setMessage('Deadline created.');
  }
  async function updateDeadline(id: string, values: Record<string, unknown>) {
    await api.patch(`/deadlines/${id}`, values);
    await deadlines.refetch();
    await overview.refetch();
    setMessage('Deadline updated.');
  }

  const clientNames = Object.fromEntries((clients.data || []).map(client => [client.id, client.name]));
  const selectedClient = (clients.data || []).find(client => client.id === clientId);
  const clientRows = clientDeadlineView.data || [];
  const today = new Date().toISOString().slice(0, 10);
  const clientCounts = clientRows.reduce((acc, row) => {
    acc[row.status] = (acc[row.status] || 0) + 1;
    if (row.status === 'pending' && row.deadline < today) acc.overdue += 1;
    if (row.status === 'pending' && row.deadline >= today) acc.upcoming += 1;
    if (row.risk_tier === 'high') acc.highRisk += 1;
    if (row.risk_tier === 'medium') acc.mediumRisk += 1;
    return acc;
  }, { pending: 0, filed: 0, missed: 0, overdue: 0, upcoming: 0, highRisk: 0, mediumRisk: 0 } as Record<string, number>);

  const overviewColumns: ColDef<OverviewRow>[] = [
    { field: 'filing_name', headerName: 'Deadline', minWidth: 170 },
    { field: 'period', headerName: 'Period' },
    { field: 'deadline', headerName: 'Date' },
    { field: 'days_until_deadline', headerName: 'Days left' },
    { field: 'high_risk_count', headerName: 'At risk' },
    { field: 'data_missing', headerName: 'Data missing' },
    { field: 'reminder_candidates', headerName: 'Can remind' },
    { field: 'reminders_sent_total', headerName: 'Sent' },
    { field: 'chronic_late', headerName: 'Chronic late' },
    { field: 'has_notice', headerName: 'Open notices' },
    { field: 'max_risk', headerName: 'Max risk', valueFormatter: p => `${Number(p.value || 0).toFixed(1)}/10` },
    { field: 'priority', headerName: 'Priority', cellRenderer: (p: ICellRendererParams<OverviewRow>) => <StatusBadge value={p.value} /> },
    {
      headerName: 'Actions', minWidth: 180, sortable: false, filter: false,
      cellRenderer: (p: ICellRendererParams<OverviewRow>) => <div className="flex h-full items-center gap-3">
        <button onClick={() => p.data && setSelected(p.data)} className="text-xs text-blue-700">Drill down</button>
        <button onClick={() => p.data && remind(p.data)} className="text-xs text-green-700">Remind pending</button>
      </div>,
    },
  ];
  const detailColumns: ColDef<DetailRow>[] = [
    { field: 'client_name', headerName: 'Client', minWidth: 190 },
    { field: 'gstin', headerName: 'GSTIN', minWidth: 160 },
    { field: 'health_score', headerName: 'Health' },
    { field: 'risk_score', headerName: 'Risk', valueFormatter: p => `${Number(p.value || 0).toFixed(1)}/10` },
    { field: 'data_received', headerName: 'Data received', valueFormatter: p => p.value ? 'Yes' : 'No' },
    { field: 'late_count_last_12m', headerName: 'Late filings' },
    { field: 'has_open_notice', headerName: 'Notice', valueFormatter: p => p.value ? 'Open' : 'None' },
    { field: 'reminders_sent', headerName: 'Reminders' },
    { field: 'reminder_eligible', headerName: 'Can remind', valueFormatter: p => p.value ? 'Yes' : 'No' },
    { field: 'last_reminder_at', headerName: 'Last reminder', valueFormatter: p => p.value || '-' },
    { field: 'status', headerName: 'Status', cellRenderer: (p: ICellRendererParams<DetailRow>) => <StatusBadge value={p.value} /> },
    {
      headerName: 'Actions', minWidth: 190, sortable: false, filter: false,
      cellRenderer: (p: ICellRendererParams<DetailRow>) => <div className="flex h-full items-center gap-3">
        {!p.data?.data_received && <button onClick={() => p.data && update(p.data.id, { data_received: true, data_source: 'manual' })} className="text-xs text-blue-700">Mark data received</button>}
        {p.data?.status !== 'filed' && <button onClick={() => p.data && update(p.data.id, { status: 'filed' })} className="text-xs text-green-700">File</button>}
      </div>,
    },
  ];
  const basicColumns: ColDef<BasicDeadline>[] = [
    { field: 'filing_name', headerName: 'Filing', minWidth: 200 },
    { field: 'client_id', headerName: 'Client', minWidth: 180, valueFormatter: p => clientNames[String(p.value)] || String(p.value || '-') },
    { field: 'filing_type', headerName: 'Type' },
    { field: 'period', headerName: 'Period' },
    { field: 'deadline', headerName: 'Due date' },
    { field: 'days_until_due', headerName: 'Days left', valueFormatter: p => `${Number(p.value || 0)}` },
    { field: 'risk_score', headerName: 'Risk', valueFormatter: p => `${Number(p.value || 0).toFixed(1)}/10` },
    { field: 'risk_tier', headerName: 'Risk tier', cellRenderer: (p: ICellRendererParams<BasicDeadline>) => <StatusBadge value={`risk_${p.value || 'low'}`} /> },
    { field: 'data_received', headerName: 'Data', valueFormatter: p => p.value ? 'Received' : 'Missing' },
    { field: 'doc_required', headerName: 'Docs' },
    { field: 'status', headerName: 'Status', cellRenderer: (p: ICellRendererParams<BasicDeadline>) => <StatusBadge value={p.value} /> },
    {
      headerName: 'Actions', minWidth: 240, sortable: false, filter: false,
      cellRenderer: (p: ICellRendererParams<BasicDeadline>) => <div className="flex h-full items-center gap-3">
        {p.data?.calendar_item_id && !p.data?.data_received && <button onClick={() => p.data?.calendar_item_id && update(p.data.calendar_item_id, { data_received: true, data_source: 'manual' })} className="text-xs text-blue-700">Data received</button>}
        {p.data?.status !== 'filed' && <button onClick={() => p.data && updateDeadline(p.data.id, { status: 'filed' })} className="text-xs text-green-700">Mark filed</button>}
        {p.data?.status !== 'missed' && <button onClick={() => p.data && updateDeadline(p.data.id, { status: 'missed' })} className="text-xs text-red-700">Missed</button>}
        {p.data?.status !== 'pending' && <button onClick={() => p.data && updateDeadline(p.data.id, { status: 'pending' })} className="text-xs text-blue-700">Reopen</button>}
      </div>,
    },
  ];

  return <div className="space-y-5">
    <PageHeader title="Advanced Compliance Calendar" subtitle="Client-aware, data-aware, and risk-aware filing operations." actions={<div className="flex gap-2"><button onClick={seedAll} className="rounded-lg border px-3 py-2 text-sm">Seed applicability</button><button onClick={score} className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white">Recalculate risk</button></div>} />
    {message && <p className="rounded-lg bg-green-50 px-3 py-2 text-sm text-green-800">{message}</p>}
    <div className="grid gap-3 md:grid-cols-5">
      {[
        ['Filings', overview.data?.length || 0],
        ['Pending clients', (overview.data || []).reduce((sum, row) => sum + row.total_pending, 0)],
        ['High risk', (overview.data || []).reduce((sum, row) => sum + row.high_risk_count, 0)],
        ['Missing data', (overview.data || []).reduce((sum, row) => sum + row.data_missing, 0)],
        ['Can remind', (overview.data || []).reduce((sum, row) => sum + row.reminder_candidates, 0)],
      ].map(([label, value]) => (
        <div key={String(label)} className="rounded-lg border border-slate-200 bg-white p-4">
          <p className="text-xs text-slate-500">{label}</p>
          <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
        </div>
      ))}
    </div>
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div>
        <h2 className="text-sm font-semibold text-slate-950">Deadline manager</h2>
        <p className="text-xs text-slate-500">Create, filter, and update statutory filing deadlines.</p>
      </div>
      <div className="grid gap-3 md:grid-cols-4">
        <ClientSelect clients={clients.data || []} value={clientId} onChange={value => { setClientId(value); setForm(prev => ({ ...prev, client_id: value })); }} />
        <select value={statusFilter} onChange={e => setStatusFilter(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="filed">Filed</option>
          <option value="missed">Missed</option>
        </select>
        <input value={form.period} onChange={e => setForm({ ...form, period: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" placeholder="2026-06" />
        <input type="date" value={form.deadline} onChange={e => setForm({ ...form, deadline: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" />
      </div>
      <div className="grid gap-3 md:grid-cols-5">
        <input value={form.filing_type} onChange={e => setForm({ ...form, filing_type: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" placeholder="GSTR3B" />
        <input value={form.filing_name} onChange={e => setForm({ ...form, filing_name: e.target.value })} className="rounded-lg border px-3 py-2 text-sm md:col-span-2" placeholder="Filing name" />
        <input value={form.doc_required} onChange={e => setForm({ ...form, doc_required: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" placeholder="Required document" />
        <button disabled={!(form.client_id || clientId)} onClick={createDeadline} className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">Create deadline</button>
      </div>
      <DataGrid rows={deadlines.data || []} columns={basicColumns} />
    </section>
    {clientId && (
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-950">{selectedClient?.name || 'Client'} deadline view</h2>
            <p className="text-xs text-slate-500">Client-specific pending, overdue, filed, and missed filings.</p>
          </div>
          <button onClick={() => clientDeadlineView.refetch()} className="rounded-lg border px-3 py-2 text-sm">Refresh client view</button>
        </div>
        <div className="grid gap-3 md:grid-cols-5">
          {[
            ['Pending', clientCounts.pending],
            ['Upcoming', clientCounts.upcoming],
            ['Overdue', clientCounts.overdue],
            ['High risk', clientCounts.highRisk],
            ['Filed', clientCounts.filed],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded-lg bg-slate-50 p-3">
              <p className="text-xs font-medium uppercase text-slate-500">{label}</p>
              <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
            </div>
          ))}
        </div>
        <DataGrid rows={clientRows} columns={basicColumns} />
      </section>
    )}
    <DataGrid rows={overview.data || []} columns={overviewColumns} pagination={false} />
    {selected && <div className="space-y-3"><h2 className="text-base font-semibold">{selected.filing_name} | {selected.period} client drill-down</h2><DataGrid rows={detail.data || []} columns={detailColumns} /></div>}
  </div>;
}
