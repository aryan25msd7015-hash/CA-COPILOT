'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Client, User } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import StatusBadge from '@/components/shared/StatusBadge';

interface VaultOverview {
  total: number;
  firm_items: number;
  client_items: number;
  expired: number;
  expiring_30_days: number;
  rotation_due: number;
  unowned: number;
  by_type: Record<string, number>;
  by_rotation: Record<string, number>;
}

interface VaultItem {
  id: string;
  client_name?: string;
  label: string;
  credential_type: string;
  username?: string;
  masked_secret?: string;
  storage_reference?: string;
  owner_email?: string;
  expires_on?: string;
  days_to_expiry?: number;
  is_expired: boolean;
  is_expiring_soon: boolean;
  rotation_status: string;
  last_used_at?: string;
  notes?: string;
}

const today = new Date().toISOString().slice(0, 10);

export default function VaultPage() {
  const [filters, setFilters] = useState({ client_id: '', credential_type: '', rotation_status: '', owner_user_id: '', expiring_within_days: '' });
  const [form, setForm] = useState({
    client_id: '',
    label: '',
    credential_type: 'dsc',
    username: '',
    secret_hint: '',
    storage_reference: '',
    owner_user_id: '',
    expires_on: today,
    notes: '',
  });

  const overview = useQuery<VaultOverview>({ queryKey: ['vault-overview'], queryFn: () => api.get('/vault/overview').then(r => r.data) });
  const items = useQuery<VaultItem[]>({
    queryKey: ['vault-items', filters],
    queryFn: () => api.get('/vault/items', {
      params: {
        client_id: filters.client_id || undefined,
        credential_type: filters.credential_type || undefined,
        rotation_status: filters.rotation_status || undefined,
        owner_user_id: filters.owner_user_id || undefined,
        expiring_within_days: filters.expiring_within_days || undefined,
      },
    }).then(r => r.data),
  });
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const users = useQuery<User[]>({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data).catch(() => []) });

  async function refreshVault() {
    await Promise.all([overview.refetch(), items.refetch()]);
  }

  async function createItem(event: FormEvent) {
    event.preventDefault();
    await api.post('/vault/items', {
      ...form,
      client_id: form.client_id || null,
      owner_user_id: form.owner_user_id || null,
      storage_reference: form.storage_reference || null,
      secret_hint: form.secret_hint || null,
      notes: form.notes || null,
    });
    setForm({ ...form, label: '', username: '', secret_hint: '', storage_reference: '', notes: '' });
    await refreshVault();
  }

  async function updateItem(item: VaultItem, rotation_status: string, last_used_now = false) {
    await api.patch(`/vault/items/${item.id}`, { rotation_status, last_used_now });
    await refreshVault();
  }

  const metrics = [
    ['Vault records', overview.data?.total || 0],
    ['Client items', overview.data?.client_items || 0],
    ['Firm items', overview.data?.firm_items || 0],
    ['Expiring 30d', overview.data?.expiring_30_days || 0],
    ['Expired', overview.data?.expired || 0],
    ['Rotation due', overview.data?.rotation_due || 0],
    ['Unowned', overview.data?.unowned || 0],
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-950">DSC & Password Vault</h1>
        <p className="text-sm text-slate-500">Track DSC expiry, portal credentials, ownership, rotation status, and secure storage references.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Credential register</h2>
              <p className="mt-1 text-xs text-slate-500">Filter by client, type, owner, rotation state, and expiry window.</p>
            </div>
            <StatusBadge value={`${items.data?.length || 0} shown`} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-5">
            <ClientSelect clients={clients.data || []} value={filters.client_id} onChange={value => setFilters({ ...filters, client_id: value })} />
            <select value={filters.credential_type} onChange={e => setFilters({ ...filters, credential_type: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All types</option>
              <option value="dsc">DSC</option>
              <option value="gst">GST</option>
              <option value="income_tax">Income Tax</option>
              <option value="mca">MCA</option>
              <option value="bank">Bank</option>
              <option value="portal">Portal</option>
            </select>
            <select value={filters.rotation_status} onChange={e => setFilters({ ...filters, rotation_status: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All rotation</option>
              <option value="current">Current</option>
              <option value="due">Due</option>
              <option value="rotating">Rotating</option>
              <option value="expired">Expired</option>
              <option value="revoked">Revoked</option>
            </select>
            <select value={filters.owner_user_id} onChange={e => setFilters({ ...filters, owner_user_id: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All owners</option>
              {(users.data || []).map(user => <option key={user.id} value={user.id}>{user.email}</option>)}
            </select>
            <select value={filters.expiring_within_days} onChange={e => setFilters({ ...filters, expiring_within_days: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">Any expiry</option>
              <option value="7">Next 7 days</option>
              <option value="30">Next 30 days</option>
              <option value="90">Next 90 days</option>
            </select>
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Label</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Type</th>
                  <th className="px-4 py-3">User</th>
                  <th className="px-4 py-3">Secret</th>
                  <th className="px-4 py-3">Expiry</th>
                  <th className="px-4 py-3">Rotation</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(items.data || []).map(item => (
                  <tr key={item.id} className={`border-t border-slate-100 ${item.is_expired ? 'bg-red-50' : item.is_expiring_soon ? 'bg-amber-50' : ''}`}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{item.label}</p>
                      <p className="text-xs text-slate-500">{item.owner_email || 'No owner'}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{item.client_name || 'Firm'}</td>
                    <td className="px-4 py-3 text-slate-600">{item.credential_type}</td>
                    <td className="px-4 py-3 text-slate-600">{item.username || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{item.masked_secret || item.storage_reference || 'reference only'}</td>
                    <td className="px-4 py-3 text-slate-600">{item.expires_on || '-'}{typeof item.days_to_expiry === 'number' ? ` (${item.days_to_expiry}d)` : ''}</td>
                    <td className="px-4 py-3"><StatusBadge value={item.rotation_status} /></td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        <button onClick={() => updateItem(item, item.rotation_status, true)} className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700">Used</button>
                        {item.rotation_status === 'current'
                          ? <button onClick={() => updateItem(item, 'due')} className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700">Due</button>
                          : <button onClick={() => updateItem(item, 'current')} className="rounded-md bg-slate-950 px-2 py-1 text-xs text-white">Current</button>}
                      </div>
                    </td>
                  </tr>
                ))}
                {!items.data?.length && !items.isLoading && (
                  <tr className="border-t"><td colSpan={8} className="px-4 py-8 text-center text-sm text-slate-500">No vault items match the filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <form onSubmit={createItem} className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Add vault item</h2>
          <div className="mt-3 space-y-3">
            <ClientSelect clients={clients.data || []} value={form.client_id} onChange={value => setForm({ ...form, client_id: value })} />
            <input required value={form.label} onChange={e => setForm({ ...form, label: e.target.value })} placeholder="Label" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <select value={form.credential_type} onChange={e => setForm({ ...form, credential_type: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="dsc">DSC</option>
              <option value="gst">GST portal</option>
              <option value="income_tax">Income Tax portal</option>
              <option value="mca">MCA portal</option>
              <option value="bank">Bank</option>
              <option value="portal">Portal</option>
            </select>
            <input value={form.username} onChange={e => setForm({ ...form, username: e.target.value })} placeholder="Username" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={form.secret_hint} onChange={e => setForm({ ...form, secret_hint: e.target.value })} placeholder="Secret hint or last characters" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={form.storage_reference} onChange={e => setForm({ ...form, storage_reference: e.target.value })} placeholder="Secure storage reference" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <select value={form.owner_user_id} onChange={e => setForm({ ...form, owner_user_id: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">No owner</option>
              {(users.data || []).map(user => <option key={user.id} value={user.id}>{user.email}</option>)}
            </select>
            <input type="date" value={form.expires_on} onChange={e => setForm({ ...form, expires_on: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Rotation or access notes" className="h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Add item</button>
          </div>
        </form>
      </div>
    </div>
  );
}
