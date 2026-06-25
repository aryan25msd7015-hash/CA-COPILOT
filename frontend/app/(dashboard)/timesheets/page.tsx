'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface Entry { id: string; client_id: string; client_name: string; date: string; hours_logged: number; task_description: string; billable: boolean; billing_rate: number; cost_rate: number; revenue: number; cost: number; margin: number; }
interface Activity { id: string; client_name: string; activity_type: string; category: string; billable_activity: boolean; duration_seconds: number; hours: number; created_at: string; }
interface Profitability { client_id: string; client_name: string; actual_hours: number; logged_hours: number; billable_hours: number; variance_hours: number; utilization_pct: number; revenue: number; cost: number; margin: number; task_breakdown: Record<string, number>; }
interface Overview { client_count: number; actual_hours: number; logged_hours: number; billable_hours: number; variance_hours: number; revenue: number; cost: number; margin: number; utilization_pct: number; negative_margin_clients: number; unlogged_actual_hours: number; }

export default function TimesheetsPage() {
  const [clientId, setClientId] = useState('');
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const [entry, setEntry] = useState({ date: new Date().toISOString().slice(0, 10), hours_logged: 1, task_description: '', billable: true, billing_rate: 1500, cost_rate: 800 });
  const [activity, setActivity] = useState({ activity_type: 'document_review', duration_seconds: 3600 });
  const [message, setMessage] = useState('');
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const entries = useQuery<Entry[]>({ queryKey: ['timesheet-entries', clientId, month], queryFn: () => api.get(`/timesheets/entries?client_id=${clientId}&month=${month}`).then(r => r.data), enabled: !!clientId });
  const activities = useQuery<Activity[]>({ queryKey: ['timesheet-activities', clientId, month], queryFn: () => api.get(`/timesheets/activities?client_id=${clientId}&month=${month}`).then(r => r.data), enabled: !!clientId });
  const profitability = useQuery<Profitability[]>({ queryKey: ['profitability', month], queryFn: () => api.get(`/timesheets/profitability?month=${month}`).then(r => r.data) });
  const overview = useQuery<Overview>({ queryKey: ['timesheet-overview', month], queryFn: () => api.get(`/timesheets/overview?month=${month}`).then(r => r.data) });
  async function refreshAll() { await Promise.all([entries.refetch(), activities.refetch(), profitability.refetch(), overview.refetch()]); }
  async function addEntry() { await api.post('/timesheets/entries', { client_id: clientId, ...entry }); await refreshAll(); setMessage('Timesheet entry saved.'); }
  async function addActivity() { await api.post('/timesheets/activities', { client_id: clientId, ...activity, details: { source: 'manual audit event' } }); await refreshAll(); setMessage('Actual platform activity recorded.'); }
  async function deleteEntry(id: string) { await api.delete(`/timesheets/entries/${id}`); await refreshAll(); setMessage('Timesheet entry removed.'); }
  const profitColumns: ColDef<Profitability>[] = [
    { field: 'client_name', headerName: 'Client', minWidth: 190 }, { field: 'actual_hours', headerName: 'Actual hours' }, { field: 'logged_hours', headerName: 'Logged hours' }, { field: 'variance_hours', headerName: 'Variance' },
    { field: 'utilization_pct', headerName: 'Billable utilization', valueFormatter: p => `${p.value}%` }, { field: 'revenue', headerName: 'Revenue', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'cost', headerName: 'Cost', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'margin', headerName: 'Margin', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}`, cellClassRules: { 'text-red-700 font-semibold': p => Number(p.value || 0) < 0 } },
  ];
  const entryColumns: ColDef<Entry>[] = [
    { field: 'date', headerName: 'Date' }, { field: 'task_description', headerName: 'Task', minWidth: 240 }, { field: 'hours_logged', headerName: 'Hours' }, { field: 'billable', headerName: 'Billable', cellRenderer: (p: ICellRendererParams<Entry>) => <StatusBadge value={p.value ? 'verified' : 'pending'} /> }, { field: 'revenue', headerName: 'Revenue', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'cost', headerName: 'Cost', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'margin', headerName: 'Margin', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { headerName: 'Actions', sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<Entry>) => <button onClick={() => p.data && deleteEntry(p.data.id)} className="text-xs text-red-700">Delete</button> },
  ];
  const activityColumns: ColDef<Activity>[] = [
    { field: 'created_at', headerName: 'Created' }, { field: 'category', headerName: 'Category', minWidth: 160 }, { field: 'activity_type', headerName: 'Activity' },
    { field: 'hours', headerName: 'Hours' }, { field: 'billable_activity', headerName: 'Billable', cellRenderer: (p: ICellRendererParams<Activity>) => <StatusBadge value={p.value ? 'verified' : 'pending'} /> },
  ];
  const metrics = [
    ['Actual hours', overview.data?.actual_hours || 0],
    ['Logged hours', overview.data?.logged_hours || 0],
    ['Billable hours', overview.data?.billable_hours || 0],
    ['Unlogged actual', overview.data?.unlogged_actual_hours || 0],
    ['Revenue', `INR ${Number(overview.data?.revenue || 0).toLocaleString('en-IN')}`],
    ['Cost', `INR ${Number(overview.data?.cost || 0).toLocaleString('en-IN')}`],
    ['Margin', `INR ${Number(overview.data?.margin || 0).toLocaleString('en-IN')}`],
    ['Utilization', `${Number(overview.data?.utilization_pct || 0).toFixed(1)}%`],
  ];
  return <div className="space-y-5">
    <PageHeader title="Article Clerk Timesheet Auditor" subtitle="Compare actual platform activity with logged hours and client-level profitability." actions={<input type="month" value={month} onChange={e => setMonth(e.target.value)} className="rounded-lg border px-3 py-2 text-sm" />} />
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    <DataGrid rows={profitability.data || []} columns={profitColumns} pagination={false} />
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><input type="date" value={entry.date} onChange={e => setEntry({ ...entry, date: e.target.value })} className="rounded border px-3 py-2 text-sm" /><input type="number" value={entry.hours_logged} onChange={e => setEntry({ ...entry, hours_logged: Number(e.target.value) })} className="w-24 rounded border px-3 py-2 text-sm" /><input value={entry.task_description} onChange={e => setEntry({ ...entry, task_description: e.target.value })} placeholder="Task description" className="min-w-64 rounded border px-3 py-2 text-sm" /><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={entry.billable} onChange={e => setEntry({ ...entry, billable: e.target.checked })} />Billable</label><button disabled={!clientId || !entry.task_description} onClick={addEntry} className="rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Log timesheet</button></div>
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><select value={activity.activity_type} onChange={e => setActivity({ ...activity, activity_type: e.target.value })} className="rounded border px-3 py-2 text-sm"><option>document_review</option><option>reconciliation_run</option><option>notice_draft</option><option>certificate_gen</option><option>query_run</option><option>upload</option><option>export</option></select><input type="number" value={activity.duration_seconds} onChange={e => setActivity({ ...activity, duration_seconds: Number(e.target.value) })} className="rounded border px-3 py-2 text-sm" /><button disabled={!clientId} onClick={addActivity} className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50">Record actual activity</button>{message && <span className="text-sm text-green-700">{message}</span>}</div>
    <DataGrid rows={entries.data || []} columns={entryColumns} />
    <DataGrid rows={activities.data || []} columns={activityColumns} />
  </div>;
}
