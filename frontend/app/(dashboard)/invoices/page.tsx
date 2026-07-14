'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { Client } from '@/types';
import { usePermission } from '@/hooks/usePermission';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';
import TaskStatusPoller from '@/components/shared/TaskStatusPoller';

interface FraudRow {
  id: string;
  client_id: string;
  client_name?: string;
  invoice_no?: string;
  vendor_name?: string;
  vendor_gstin?: string;
  amount: number;
  date?: string;
  fraud_flag?: string;
  fraud_review_status: string;
  fraud_review_note?: string;
  fraud_scanned_at?: string;
}
interface SummaryBucket { count: number; amount: number; }
type Summary = Record<string, SummaryBucket>;

const STATUSES = ['open', 'rescanning', 'confirmed', 'needs_followup', 'false_positive', 'cleared'];

export default function InvoicesPage() {
  const canClear = usePermission('clear:fraud_flag');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [status, setStatus] = useState('open');
  const [clientId, setClientId] = useState('');
  const [search, setSearch] = useState('');
  const [minAmount, setMinAmount] = useState('');
  const [noteById, setNoteById] = useState<Record<string, string>>({});
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const summary = useQuery<Summary>({ queryKey: ['fraud-summary'], queryFn: () => api.get('/invoices/fraud-summary').then(r => r.data) });
  const queue = useQuery<FraudRow[]>({
    queryKey: ['fraud-queue', status, clientId, search, minAmount],
    queryFn: () => api.get('/invoices/fraud-queue', {
      params: {
        review_status: status,
        include_cleared: status === 'cleared',
        ...(clientId ? { client_id: clientId } : {}),
        ...(search.trim() ? { q: search.trim() } : {}),
        ...(Number(minAmount) > 0 ? { min_amount: Number(minAmount) } : {}),
        limit: 1000,
      },
    }).then(r => r.data),
  });

  const refresh = useCallback(async () => {
    await Promise.all([queue.refetch(), summary.refetch()]);
  }, [queue, summary]);

  const review = useCallback(async (row: FraudRow, reviewStatus: string) => {
    await api.patch(`/invoices/${row.id}/review`, {
      review_status: reviewStatus,
      note: noteById[row.id] || undefined,
    });
    await refresh();
  }, [noteById, refresh]);

  const rescan = useCallback(async (row: FraudRow) => {
    const response = await api.post(`/invoices/${row.id}/rescan`);
    setTaskId(response.data.task_id);
    await refresh();
  }, [refresh]);

  const clear = useCallback(async (row: FraudRow) => {
    await api.patch(`/invoices/${row.id}/clear-flag`);
    await refresh();
  }, [refresh]);

  const columns = useMemo<ColDef<FraudRow>[]>(() => [
    { field: 'invoice_no', headerName: 'Invoice', minWidth: 150, valueFormatter: p => String(p.value || '-') },
    { field: 'client_name', headerName: 'Client', minWidth: 190, valueFormatter: p => String(p.value || p.data?.client_id || '-') },
    { field: 'vendor_name', headerName: 'Vendor', minWidth: 180, valueFormatter: p => String(p.value || p.data?.vendor_gstin || '-') },
    { field: 'vendor_gstin', headerName: 'GSTIN', minWidth: 165 },
    { field: 'amount', headerName: 'Amount', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'fraud_review_status', headerName: 'Status', minWidth: 140, cellRenderer: (p: ICellRendererParams<FraudRow>) => <StatusBadge value={p.data?.fraud_review_status} /> },
    { field: 'fraud_flag', headerName: 'Reason', minWidth: 300, cellClass: 'text-red-700', valueFormatter: p => String(p.value || '-') },
    { field: 'fraud_scanned_at', headerName: 'Scanned', valueFormatter: p => p.value ? new Date(p.value).toLocaleString('en-IN') : '-' },
    {
      headerName: 'Actions',
      sortable: false,
      filter: false,
      minWidth: 470,
      cellRenderer: (p: ICellRendererParams<FraudRow>) => <div className="flex h-full items-center gap-2">
        <input
          value={p.data ? noteById[p.data.id] || '' : ''}
          onChange={event => p.data && setNoteById(prev => ({ ...prev, [p.data!.id]: event.target.value }))}
          placeholder="Review note"
          className="w-36 rounded border px-2 py-1 text-xs"
        />
        {p.data && <button onClick={() => rescan(p.data!)} className="text-xs text-blue-700">Rescan</button>}
        {p.data && <button onClick={() => review(p.data!, 'confirmed')} className="text-xs text-red-700">Confirm</button>}
        {p.data && <button onClick={() => review(p.data!, 'needs_followup')} className="text-xs text-amber-700">Follow up</button>}
        {p.data && <button onClick={() => review(p.data!, 'false_positive')} className="text-xs text-green-700">False positive</button>}
        {canClear && p.data && <button onClick={() => clear(p.data!)} className="text-xs text-gray-700">Clear</button>}
      </div>,
    },
  ], [canClear, clear, noteById, rescan, review]);

  return <div className="space-y-5">
    <PageHeader title="Invoice Fraud Queue" subtitle="Invoices that failed GSTIN, tax arithmetic, duplicate, or fraud-risk checks." actions={<TaskStatusPoller taskId={taskId} onSuccess={refresh} />} />
    <div className="grid gap-3 md:grid-cols-6">
      {STATUSES.map(item => <button key={item} onClick={() => setStatus(item)} className={`rounded-xl border p-4 text-left ${status === item ? 'border-gray-900 bg-gray-900 text-white' : 'bg-white text-gray-900'}`}>
        <p className="text-xs opacity-70">{item.replaceAll('_', ' ')}</p>
        <p className="mt-1 text-2xl font-semibold">{summary.data?.[item]?.count || 0}</p>
      </button>)}
    </div>
    <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-3">
      <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search invoice, client, vendor, reason" className="min-w-64 rounded-lg border px-3 py-2 text-sm" />
      <select value={clientId} onChange={event => setClientId(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
        <option value="">All clients</option>
        {(clients.data || []).map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
      </select>
      <input value={minAmount} onChange={event => setMinAmount(event.target.value)} type="number" min="0" placeholder="Minimum amount" className="w-40 rounded-lg border px-3 py-2 text-sm" />
    </div>
    <DataGrid rows={queue.data || []} columns={columns} pageSize={20} />
  </div>;
}
