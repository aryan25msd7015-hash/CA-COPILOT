'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientTable from '@/components/clients/ClientTable';

interface WorkloadDistribution {
  distribution_anomalies: {
    is_imbalanced: boolean;
    std_dev_units: number;
    overloaded_resource_count: number;
  };
  client_workload_complexities: {
    client_id: string;
    client_name: string;
    complexity_index: number;
    risk_band: string;
    open_tasks: number;
    overdue_deadlines: number;
    failed_documents: number;
    routing_suggestion: { suggested_email?: string; reason: string };
  }[];
  team_utilization_profiles: {
    user_id: string;
    email: string;
    total_units: number;
    utilization_pct: number;
    status: string;
  }[];
}

const EMPTY_FORM = {
  name: '',
  entity_type: 'pvt_ltd',
  gstin: '',
  pan: '',
  tan: '',
  cin: '',
  email: '',
  whatsapp_number: '',
  industry: '',
  registered_office: '',
};

function clientCreateErrorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (Array.isArray(detail)) {
    return detail
      .map(item => {
        const issue = item as { loc?: string[]; msg?: string };
        const field = issue.loc?.filter(part => part !== 'body').join('.') || 'field';
        return `${field}: ${issue.msg || 'Invalid value'}`;
      })
      .join(', ');
  }
  if (typeof detail === 'string') return detail;
  if ((error as { message?: string })?.message === 'Network Error') {
    return 'Network error: backend is not reachable. Check that http://localhost:8000 is running.';
  }
  return 'Could not create client. Check GSTIN, PAN, TAN, email, WhatsApp number, and duplicate PAN/GSTIN.';
}

export default function ClientsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [createError, setCreateError] = useState('');
  const [createMessage, setCreateMessage] = useState('');

  const { data: clients = [], isLoading } = useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  });
  const workload = useQuery<WorkloadDistribution>({
    queryKey: ['client-workload-distribution'],
    queryFn: () => api.get('/clients/workload/distribution').then(r => r.data),
  });

  const filtered = clients.filter(client =>
    client.name.toLowerCase().includes(search.toLowerCase()) ||
    (client.gstin || '').toLowerCase().includes(search.toLowerCase()),
  );

  async function createClient(event: React.FormEvent) {
    event.preventDefault();
    setCreateError('');
    setCreateMessage('');
    const payload = Object.fromEntries(
      Object.entries(form).filter(([, value]) => String(value).trim() !== ''),
    );
    try {
      await api.post('/clients', payload);
      setForm(EMPTY_FORM);
      setShowCreate(false);
      setCreateMessage('Client created and deadlines seeded.');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['clients'] }),
        queryClient.invalidateQueries({ queryKey: ['client-workload-distribution'] }),
      ]);
    } catch (error: unknown) {
      setCreateError(clientCreateErrorMessage(error));
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-gray-900">Clients</h1>
        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search by name or GSTIN..."
            value={search}
            onChange={event => setSearch(event.target.value)}
            className="w-64 rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <button onClick={() => setShowCreate(!showCreate)} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white">
            Add client
          </button>
        </div>
      </div>
      {createMessage && <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{createMessage}</p>}

      {showCreate && (
        <form onSubmit={createClient} className="grid gap-3 rounded-xl border bg-white p-4 md:grid-cols-3">
          <input required value={form.name} onChange={event => setForm({ ...form, name: event.target.value })} placeholder="Client name" className="rounded-lg border px-3 py-2 text-sm" />
          <select value={form.entity_type} onChange={event => setForm({ ...form, entity_type: event.target.value })} className="rounded-lg border px-3 py-2 text-sm">
            <option value="pvt_ltd">Private limited company</option>
            <option value="llp">LLP</option>
            <option value="partnership">Partnership firm</option>
            <option value="proprietorship">Proprietorship</option>
            <option value="trust">Trust</option>
          </select>
          {(['gstin', 'pan', 'tan', 'cin', 'email', 'whatsapp_number', 'industry', 'registered_office'] as const).map(key => (
            <input
              key={key}
              value={form[key]}
              onChange={event => setForm({ ...form, [key]: event.target.value })}
              placeholder={key.replaceAll('_', ' ')}
              className="rounded-lg border px-3 py-2 text-sm"
            />
          ))}
          <button className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white">
            Create client and seed deadlines
          </button>
          {createError && <p className="md:col-span-3 rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{createError}</p>}
        </form>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]">
        <section className="rounded-xl border bg-white p-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900">Workload complexity</h2>
            <span className={`rounded-full px-2 py-1 text-xs font-medium ${workload.data?.distribution_anomalies.is_imbalanced ? 'bg-amber-100 text-amber-800' : 'bg-emerald-100 text-emerald-800'}`}>
              {workload.data?.distribution_anomalies.is_imbalanced ? 'Imbalanced' : 'Balanced'}
            </span>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-xs uppercase text-gray-500">
                <tr>
                  <th className="py-2 pr-3">Client</th>
                  <th className="py-2 pr-3">Complexity</th>
                  <th className="py-2 pr-3">Risk</th>
                  <th className="py-2 pr-3">Open work</th>
                  <th className="py-2 pr-3">Route to</th>
                </tr>
              </thead>
              <tbody>
                {(workload.data?.client_workload_complexities || []).slice(0, 6).map(row => (
                  <tr key={row.client_id} className="border-t">
                    <td className="py-2 pr-3 font-medium text-gray-900">{row.client_name}</td>
                    <td className="py-2 pr-3 text-gray-700">{row.complexity_index}</td>
                    <td className="py-2 pr-3 text-gray-700">{row.risk_band}</td>
                    <td className="py-2 pr-3 text-gray-700">{row.open_tasks} tasks, {row.overdue_deadlines} overdue</td>
                    <td className="py-2 pr-3 text-gray-700">{row.routing_suggestion.suggested_email || '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-xl border bg-white p-4">
          <h2 className="text-sm font-semibold text-gray-900">Team load</h2>
          <div className="mt-3 space-y-3">
            {(workload.data?.team_utilization_profiles || []).slice(0, 5).map(row => (
              <div key={row.user_id}>
                <div className="flex justify-between text-xs">
                  <span className="font-medium text-gray-700">{row.email}</span>
                  <span className="text-gray-500">{row.total_units} units</span>
                </div>
                <div className="mt-1 h-2 rounded-full bg-gray-100">
                  <div className={`h-2 rounded-full ${row.status === 'overloaded' ? 'bg-rose-500' : 'bg-blue-500'}`} style={{ width: `${Math.min(100, row.utilization_pct)}%` }} />
                </div>
              </div>
            ))}
            {!workload.data?.team_utilization_profiles.length && <p className="text-xs text-gray-400">No active team load yet.</p>}
          </div>
        </section>
      </div>

      <div className="rounded-xl border bg-white p-4">
        {isLoading ? (
          <p className="text-sm text-gray-400">Loading...</p>
        ) : (
          <ClientTable clients={filtered} onClientClick={client => router.push(`/clients/${client.id}`)} />
        )}
      </div>
    </div>
  );
}
