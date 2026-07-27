'use client';

import { FormEvent, ReactNode, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client } from '@/types';
import { canPerform } from '@/lib/permissions';
import { useAuth } from '@/hooks/useAuth';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

type Field =
  | { key: string; label: string; type?: 'text' | 'textarea' | 'select' | 'number' | 'date'; options?: string[]; required?: boolean }
  ;

interface GapModulePageProps {
  title: string;
  subtitle: string;
  endpoint: string;
  queryKey: string;
  columns: ColDef[];
  createFields: Field[];
  defaults?: Record<string, string | number | boolean>;
  requireClient?: boolean;
  primaryActionLabel?: string;
  extraActions?: (ctx: {
    clientId: string;
    refetch: () => void;
    canApprove: boolean;
  }) => ReactNode;
  rowActions?: (row: Record<string, unknown>, helpers: {
    patch: (id: string, body: Record<string, unknown>) => Promise<void>;
    canApprove: boolean;
  }) => ReactNode;
}

export default function GapModulePage({
  title,
  subtitle,
  endpoint,
  queryKey,
  columns,
  createFields,
  defaults = {},
  requireClient = true,
  primaryActionLabel = 'Create',
  extraActions,
  rowActions,
}: GapModulePageProps) {
  const { user } = useAuth();
  const qc = useQueryClient();
  const [clientId, setClientId] = useState('');
  const [form, setForm] = useState<Record<string, string>>(() =>
    Object.fromEntries(Object.entries(defaults).map(([k, v]) => [k, String(v)])),
  );
  const [message, setMessage] = useState('');
  const canApprove = canPerform(user?.role, 'approve:engagement')
    || canPerform(user?.role, 'close:observation')
    || canPerform(user?.role, 'signoff:checklist')
    || user?.role === 'manager'
    || user?.role === 'partner';

  const clients = useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  });

  const listPath = clientId && requireClient
    ? `${endpoint}?client_id=${clientId}`
    : endpoint;

  const rows = useQuery({
    queryKey: [queryKey, clientId],
    queryFn: () => api.get(listPath).then(r => r.data),
    enabled: !requireClient || !!clientId || endpoint.includes('peer-review') || endpoint.includes('knowledge') || endpoint.includes('risk-scores'),
  });

  const create = useMutation({
    mutationFn: async () => {
      const body: Record<string, unknown> = { ...form };
      if (requireClient) body.client_id = clientId;
      for (const field of createFields) {
        if (field.type === 'number' && body[field.key] !== undefined && body[field.key] !== '') {
          body[field.key] = Number(body[field.key]);
        }
      }
      await api.post(endpoint, body);
    },
    onSuccess: async () => {
      setMessage('Saved.');
      setForm(Object.fromEntries(Object.entries(defaults).map(([k, v]) => [k, String(v)])));
      await qc.invalidateQueries({ queryKey: [queryKey] });
    },
    onError: (err: unknown) => {
      setMessage(err instanceof Error ? err.message : 'Save failed');
    },
  });

  async function patch(id: string, body: Record<string, unknown>) {
    await api.patch(`${endpoint}/${id}`, body);
    await qc.invalidateQueries({ queryKey: [queryKey] });
    setMessage('Updated.');
  }

  const gridColumns = useMemo(() => {
    if (!rowActions) return columns;
    return [
      ...columns,
      {
        headerName: 'Actions',
        minWidth: 160,
        cellRenderer: (p: { data?: Record<string, unknown> }) =>
          p.data ? rowActions(p.data, { patch, canApprove }) : null,
      },
    ];
  }, [columns, rowActions, canApprove]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (requireClient && !clientId) {
      setMessage('Select a client first.');
      return;
    }
    create.mutate();
  }

  return (
    <div className="space-y-5">
      <PageHeader title={title} subtitle={subtitle} />
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-line bg-white/5 p-4">
        {requireClient && (
          <ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} />
        )}
        {extraActions?.({
          clientId,
          refetch: () => { void rows.refetch(); },
          canApprove,
        })}
      </div>
      <form onSubmit={onSubmit} className="grid gap-3 rounded-xl border border-line bg-white/5 p-4 md:grid-cols-3">
        {createFields.map(field => {
          if (field.type === 'textarea') {
            return (
              <textarea
                key={field.key}
                value={form[field.key] || ''}
                onChange={e => setForm({ ...form, [field.key]: e.target.value })}
                placeholder={field.label}
                className="md:col-span-2 rounded-lg border border-line bg-transparent px-3 py-2 text-sm"
                required={field.required}
              />
            );
          }
          if (field.type === 'select') {
            return (
              <select
                key={field.key}
                value={form[field.key] || ''}
                onChange={e => setForm({ ...form, [field.key]: e.target.value })}
                className="rounded-lg border border-line bg-transparent px-3 py-2 text-sm"
              >
                {(field.options || []).map(opt => <option key={opt} value={opt}>{opt}</option>)}
              </select>
            );
          }
          return (
            <input
              key={field.key}
              type={field.type || 'text'}
              value={form[field.key] || ''}
              onChange={e => setForm({ ...form, [field.key]: e.target.value })}
              placeholder={field.label}
              className="rounded-lg border border-line bg-transparent px-3 py-2 text-sm"
              required={field.required}
            />
          );
        })}
        <button type="submit" className="rounded-lg bg-cyan-600 px-3 py-2 text-sm text-white disabled:opacity-50" disabled={create.isPending}>
          {primaryActionLabel}
        </button>
      </form>
      {message && <p className="text-sm text-cyan-300">{message}</p>}
      <DataGrid rows={rows.data || []} columns={gridColumns} />
    </div>
  );
}
