'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import StatusBadge from '@/components/shared/StatusBadge';

interface ReportsOverview {
  clients: number;
  high_risk_clients: number;
  open_tasks: number;
  overdue_tasks: number;
  tasks_due_7_days: number;
  outstanding: number;
  overdue_collections: number;
  portal_pending: number;
  vault_expiring: number;
  saved_views: number;
  by_task_status: Record<string, number>;
  by_service_type: Record<string, number>;
  by_invoice_status: Record<string, number>;
}

interface SavedView {
  id: string;
  name: string;
  view_type: string;
  filters: Record<string, unknown>;
  columns: string[];
  is_shared: boolean;
  user_email?: string;
  filter_count: number;
  column_count: number;
  created_at?: string;
}

function money(value: number) {
  return `INR ${Number(value || 0).toLocaleString('en-IN')}`;
}

export default function ReportsPage() {
  const [viewFilters, setViewFilters] = useState({ view_type: '', shared: '' });
  const [form, setForm] = useState({
    name: 'Partner weekly review',
    view_type: 'partner_dashboard',
    is_shared: true,
    filters: '{\n  "period": "current",\n  "risk": "all"\n}',
    columns: 'client, owner, due_date, risk, amount',
  });
  const [message, setMessage] = useState('');

  const overview = useQuery<ReportsOverview>({ queryKey: ['reports-overview'], queryFn: () => api.get('/reports/overview').then(r => r.data) });
  const savedViews = useQuery<SavedView[]>({
    queryKey: ['saved-views', viewFilters],
    queryFn: () => api.get('/reports/saved-views', {
      params: {
        view_type: viewFilters.view_type || undefined,
        shared: viewFilters.shared || undefined,
      },
    }).then(r => r.data),
  });

  async function createView(event: FormEvent) {
    event.preventDefault();
    setMessage('');
    let filters: Record<string, unknown> = {};
    try {
      filters = JSON.parse(form.filters);
    } catch {
      setMessage('Filters must be valid JSON.');
      return;
    }
    await api.post('/reports/saved-views', {
      name: form.name,
      view_type: form.view_type,
      is_shared: form.is_shared,
      filters,
      columns: form.columns.split(',').map(item => item.trim()).filter(Boolean),
    });
    setMessage('Saved view created.');
    await Promise.all([savedViews.refetch(), overview.refetch()]);
  }

  const metrics = [
    ['Clients', overview.data?.clients || 0],
    ['High risk', overview.data?.high_risk_clients || 0],
    ['Open tasks', overview.data?.open_tasks || 0],
    ['Overdue tasks', overview.data?.overdue_tasks || 0],
    ['Due 7 days', overview.data?.tasks_due_7_days || 0],
    ['Outstanding', money(overview.data?.outstanding || 0)],
    ['Overdue collections', money(overview.data?.overdue_collections || 0)],
    ['Saved views', overview.data?.saved_views || 0],
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-950">Reports & Saved Views</h1>
        <p className="text-sm text-slate-500">Portfolio risk, workload, collections, portal requests, credential expiry, and reusable partner views.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {[
          ['Task status', overview.data?.by_task_status || {}],
          ['Service mix', overview.data?.by_service_type || {}],
          ['Invoice status', overview.data?.by_invoice_status || {}],
        ].map(([title, data]) => (
          <section key={title as string} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">{title as string}</h2>
            <div className="mt-3 space-y-2">
              {Object.entries(data as Record<string, number>).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between rounded-md bg-slate-50 px-3 py-2 text-sm">
                  <span className="text-slate-600">{key}</span>
                  <span className="font-semibold text-slate-950">{value}</span>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_.75fr]">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Saved views</h2>
              <p className="mt-1 text-xs text-slate-500">Reusable report definitions for partners, managers, and firm-wide dashboards.</p>
            </div>
            <StatusBadge value={`${savedViews.data?.length || 0} views`} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            <select value={viewFilters.view_type} onChange={e => setViewFilters({ ...viewFilters, view_type: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All types</option>
              <option value="partner_dashboard">Partner dashboard</option>
              <option value="workload">Workload</option>
              <option value="collections">Collections</option>
              <option value="compliance">Compliance</option>
              <option value="client_portal">Client portal</option>
            </select>
            <select value={viewFilters.shared} onChange={e => setViewFilters({ ...viewFilters, shared: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">Shared and private</option>
              <option value="true">Shared</option>
              <option value="false">Private</option>
            </select>
          </div>
          <div className="mt-4 divide-y divide-slate-100">
            {(savedViews.data || []).map(view => (
              <div key={view.id} className="flex flex-wrap items-start justify-between gap-3 py-4">
                <div>
                  <p className="text-sm font-semibold text-slate-900">{view.name}</p>
                  <p className="text-xs text-slate-500">{view.view_type} / {view.column_count} columns / {view.filter_count} filters / {view.user_email || 'owner'}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {(view.columns || []).slice(0, 6).map(column => <span key={column} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{column}</span>)}
                  </div>
                </div>
                <StatusBadge value={view.is_shared ? 'shared' : 'private'} />
              </div>
            ))}
            {!savedViews.data?.length && !savedViews.isLoading && <p className="py-8 text-center text-sm text-slate-500">No saved views match the filters.</p>}
          </div>
        </section>

        <form onSubmit={createView} className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Save report view</h2>
          <div className="mt-3 space-y-3">
            <input required value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <select value={form.view_type} onChange={e => setForm({ ...form, view_type: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="partner_dashboard">Partner dashboard</option>
              <option value="workload">Workload</option>
              <option value="collections">Collections</option>
              <option value="compliance">Compliance</option>
              <option value="client_portal">Client portal</option>
            </select>
            <textarea value={form.filters} onChange={e => setForm({ ...form, filters: e.target.value })} className="h-32 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs" />
            <textarea value={form.columns} onChange={e => setForm({ ...form, columns: e.target.value })} className="h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={form.is_shared} onChange={e => setForm({ ...form, is_shared: e.target.checked })} />
              Share with firm
            </label>
            <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Save view</button>
            {message && <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">{message}</p>}
          </div>
        </form>
      </div>
    </div>
  );
}
