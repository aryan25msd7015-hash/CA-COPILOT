'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import StatusBadge from '@/components/shared/StatusBadge';

interface ImportJob {
  id: string;
  client_name?: string;
  import_type: string;
  source_name: string;
  status: string;
  mapping: Record<string, string>;
  sample_rows: Record<string, unknown>[];
  validation_errors: { field?: string; row?: number; message: string }[];
  records_total: number;
  records_valid: number;
  records_invalid: number;
  records_imported: number;
  valid_ratio: number;
  created_at?: string;
  completed_at?: string;
}

interface ImportConfig {
  import_types: { key: string; required_fields: string[]; sample_row: Record<string, string> }[];
  max_preview_rows: number;
}

interface ImportOverview {
  jobs: number;
  validated: number;
  needs_mapping: number;
  imported: number;
  failed: number;
  records_total: number;
  records_valid: number;
  records_imported: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
}

const DEFAULT_ROWS = JSON.stringify([
  { date: '2026-06-01', voucher_no: 'PUR-1001', party_name: 'Demo Supplier Pvt Ltd', amount: 49500 },
], null, 2);

export default function ImportsPage() {
  const [filters, setFilters] = useState({ status: '', import_type: '', client_id: '' });
  const [form, setForm] = useState({
    client_id: '',
    import_type: 'tally_vouchers',
    source_name: 'Tally purchase register',
    mapping: '{}',
    sample_rows: DEFAULT_ROWS,
  });
  const [message, setMessage] = useState('');

  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const config = useQuery<ImportConfig>({ queryKey: ['imports-config'], queryFn: () => api.get('/imports/config').then(r => r.data) });
  const overview = useQuery<ImportOverview>({ queryKey: ['imports-overview'], queryFn: () => api.get('/imports/overview').then(r => r.data) });
  const jobs = useQuery<ImportJob[]>({
    queryKey: ['import-jobs', filters],
    queryFn: () => api.get('/imports/jobs', {
      params: {
        status: filters.status || undefined,
        import_type: filters.import_type || undefined,
        client_id: filters.client_id || undefined,
      },
    }).then(r => r.data),
  });

  const selectedType = useMemo(() => {
    return config.data?.import_types.find(item => item.key === form.import_type);
  }, [config.data, form.import_type]);

  function loadSample(importType: string) {
    const row = config.data?.import_types.find(item => item.key === importType)?.sample_row;
    setForm({
      ...form,
      import_type: importType,
      sample_rows: JSON.stringify([row || {}], null, 2),
      mapping: '{}',
    });
  }

  async function refreshImports() {
    await Promise.all([overview.refetch(), jobs.refetch()]);
  }

  async function createJob(event: FormEvent) {
    event.preventDefault();
    setMessage('');
    let rows: Record<string, unknown>[] = [];
    let mapping: Record<string, string> = {};
    try {
      rows = JSON.parse(form.sample_rows) as Record<string, unknown>[];
      if (!Array.isArray(rows)) throw new Error('Expected array');
    } catch {
      setMessage('Sample rows must be a JSON array.');
      return;
    }
    try {
      mapping = JSON.parse(form.mapping) as Record<string, string>;
      if (!mapping || Array.isArray(mapping)) throw new Error('Expected object');
    } catch {
      setMessage('Mapping must be a JSON object.');
      return;
    }
    const response = await api.post('/imports/jobs', {
      client_id: form.client_id || null,
      import_type: form.import_type,
      source_name: form.source_name,
      mapping,
      sample_rows: rows,
    });
    setMessage(`Import ${response.data.status}: ${response.data.records_valid}/${response.data.records_total} valid rows.`);
    await refreshImports();
  }

  async function commitJob(job: ImportJob) {
    const response = await api.post(`/imports/jobs/${job.id}/commit`);
    setMessage(`Committed ${response.data.records_imported} rows from ${job.source_name}.`);
    await refreshImports();
  }

  const metrics = [
    ['Jobs', overview.data?.jobs || 0],
    ['Validated', overview.data?.validated || 0],
    ['Needs mapping', overview.data?.needs_mapping || 0],
    ['Imported', overview.data?.imported || 0],
    ['Rows valid', `${overview.data?.records_valid || 0}/${overview.data?.records_total || 0}`],
    ['Rows imported', overview.data?.records_imported || 0],
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-950">Guided Imports</h1>
        <p className="text-sm text-slate-500">Validate Tally, GST, client master, billing, and attendance imports before they enter the review workflow.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Import jobs</h2>
              <p className="mt-1 text-xs text-slate-500">Validation history, mapping issues, and committed row counts.</p>
            </div>
            <StatusBadge value={`${jobs.data?.length || 0} jobs`} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All statuses</option>
              <option value="validated">Validated</option>
              <option value="needs_mapping">Needs mapping</option>
              <option value="imported">Imported</option>
              <option value="failed">Failed</option>
            </select>
            <select value={filters.import_type} onChange={e => setFilters({ ...filters, import_type: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All types</option>
              {(config.data?.import_types || []).map(type => <option key={type.key} value={type.key}>{type.key}</option>)}
            </select>
            <ClientSelect clients={clients.data || []} value={filters.client_id} onChange={value => setFilters({ ...filters, client_id: value })} />
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Source</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">Rows</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(jobs.data || []).map(job => (
                  <tr key={job.id} className="border-t border-slate-100 align-top">
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{job.source_name}</p>
                      {!!job.validation_errors.length && <p className="text-xs text-red-600">{job.validation_errors[0].message}</p>}
                      {!!Object.keys(job.mapping || {}).length && <p className="mt-1 text-xs text-slate-500">Mapping: {Object.entries(job.mapping).map(([k, v]) => `${k}->${v}`).join(', ')}</p>}
                    </td>
                    <td className="px-4 py-3 text-slate-600">{job.client_name || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{job.import_type}</td>
                    <td className="px-4 py-3 text-slate-600">{job.records_valid}/{job.records_total} <span className="text-xs text-slate-400">({job.valid_ratio}%)</span></td>
                    <td className="px-4 py-3"><StatusBadge value={job.status} /></td>
                    <td className="px-4 py-3 text-right">
                      {job.status === 'validated' && <button onClick={() => commitJob(job)} className="rounded-md bg-slate-950 px-2 py-1 text-xs text-white">Commit</button>}
                    </td>
                  </tr>
                ))}
                {!jobs.data?.length && !jobs.isLoading && (
                  <tr className="border-t"><td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">No import jobs match the filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <form onSubmit={createJob} className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Validate import</h2>
          <div className="mt-3 space-y-3">
            <ClientSelect clients={clients.data || []} value={form.client_id} onChange={value => setForm({ ...form, client_id: value })} />
            <select value={form.import_type} onChange={e => loadSample(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              {(config.data?.import_types || []).map(type => <option key={type.key} value={type.key}>{type.key}</option>)}
            </select>
            <div className="rounded-md bg-slate-50 p-3">
              <p className="text-xs font-semibold text-slate-600">Required fields</p>
              <div className="mt-2 flex flex-wrap gap-1">
                {(selectedType?.required_fields || []).map(field => <span key={field} className="rounded-full bg-white px-2 py-1 text-xs text-slate-600">{field}</span>)}
              </div>
            </div>
            <input value={form.source_name} onChange={e => setForm({ ...form, source_name: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <textarea value={form.mapping} onChange={e => setForm({ ...form, mapping: e.target.value })} className="h-24 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs" />
            <textarea value={form.sample_rows} onChange={e => setForm({ ...form, sample_rows: e.target.value })} className="h-64 w-full rounded-md border border-slate-300 px-3 py-2 font-mono text-xs" />
            <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Validate rows</button>
            {message && <p className="rounded-md bg-slate-50 px-3 py-2 text-xs text-slate-600">{message}</p>}
          </div>
        </form>
      </div>
    </div>
  );
}
