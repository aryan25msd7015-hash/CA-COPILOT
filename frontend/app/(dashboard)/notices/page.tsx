'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { BrainCircuit } from 'lucide-react';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import FileUploadZone from '@/components/shared/FileUploadZone';
import PageHeader from '@/components/shared/PageHeader';
import TaskStatusPoller from '@/components/shared/TaskStatusPoller';
import StatusBadge from '@/components/shared/StatusBadge';
import AiSummaryModal from '@/components/ai/AiSummaryModal';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';

interface DraftResult {
  draft?: string;
  provider?: string;
  notice_data?: Record<string, string | null>;
  validation?: { valid: boolean; cited?: string[]; unverified?: string[]; confidence?: string; provider?: string };
  source_chunks?: string[];
}
interface NoticeRow {
  id: string;
  client_id: string;
  client_name?: string;
  document_status: string;
  draft_status: string;
  task_id?: string;
  original_filename?: string;
  draft_error?: string;
  draft_queued_at?: string;
  draft_started_at?: string;
  draft_completed_at?: string;
  created_at?: string;
  file_size_bytes?: string;
  mime_type?: string;
  notice_data?: Record<string, string | null>;
  draft_result?: DraftResult;
}

const STATUS_OPTIONS = ['all', 'waiting_for_ocr', 'ready_to_draft', 'queued', 'generating', 'ready', 'failed'];

export default function NoticesPage() {
  const [clientId, setClientId] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<DraftResult | null>(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [listClientId, setListClientId] = useState('');
  const [search, setSearch] = useState('');
  const [aiTarget, setAiTarget] = useState<NoticeRow | null>(null);
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const notices = useQuery<NoticeRow[]>({
    queryKey: ['notices', statusFilter, listClientId, search],
    queryFn: () => api.get('/notices', {
      params: {
        ...(statusFilter === 'all' ? {} : { draft_status: statusFilter }),
        ...(listClientId ? { client_id: listClientId } : {}),
        ...(search.trim() ? { q: search.trim() } : {}),
      },
    }).then(r => r.data),
    refetchInterval: 5000,
  });
  const rows = notices.data || [];
  const readyCount = rows.filter(row => row.draft_status === 'ready').length;
  const failedCount = rows.filter(row => row.draft_status === 'failed').length;
  const activeCount = rows.filter(row => ['queued', 'generating'].includes(row.draft_status)).length;

  const columns: ColDef<NoticeRow>[] = [
    { field: 'original_filename', headerName: 'Notice', minWidth: 180, valueFormatter: p => String(p.value || p.data?.id || '-') },
    { field: 'client_name', headerName: 'Client', minWidth: 190, valueFormatter: p => String(p.value || '-') },
    {
      field: 'draft_status',
      headerName: 'Draft status',
      minWidth: 150,
      cellRenderer: (p: ICellRendererParams<NoticeRow>) => <StatusBadge value={p.data?.draft_status} />,
    },
    { field: 'document_status', headerName: 'Document', minWidth: 130, cellRenderer: (p: ICellRendererParams<NoticeRow>) => <StatusBadge value={p.data?.document_status} /> },
    { field: 'notice_data.notice_type', headerName: 'Type', valueGetter: p => p.data?.notice_data?.notice_type || '-' },
    { field: 'notice_data.section', headerName: 'Section', valueGetter: p => p.data?.notice_data?.section || '-' },
    { field: 'notice_data.demand_amt', headerName: 'Demand', valueGetter: p => p.data?.notice_data?.demand_amt || '-' },
    { field: 'notice_data.due_date', headerName: 'Due date', valueGetter: p => p.data?.notice_data?.due_date || '-' },
    { field: 'draft_queued_at', headerName: 'Queued', valueFormatter: p => p.value ? new Date(p.value).toLocaleString('en-IN') : '-' },
    { field: 'draft_completed_at', headerName: 'Completed', valueFormatter: p => p.value ? new Date(p.value).toLocaleString('en-IN') : '-' },
    { field: 'draft_error', headerName: 'Error', minWidth: 220, valueFormatter: p => String(p.value || '-') },
    {
      headerName: 'Actions',
      minWidth: 220,
      sortable: false,
      filter: false,
      cellRenderer: (p: ICellRendererParams<NoticeRow>) => <div className="flex h-full items-center gap-2">
        <button onClick={() => { if (p.data) { setDocumentId(p.data.id); setResult(p.data.draft_result || null); setTaskId(p.data.task_id || null); } }} className="text-xs text-blue-700">Open</button>
        {p.data && <button
          onClick={() => setAiTarget(p.data!)}
          className="flex items-center gap-1 rounded border border-cyan-700 bg-cyan-950/40 px-1.5 py-0.5 text-xs text-cyan-200 hover:bg-cyan-900/50"
          data-testid={`btn-ai-notice-${p.data.id}`}
        >
          <BrainCircuit className="h-3 w-3" /> AI Summary
        </button>}
      </div>,
    },
  ];

  async function draft() {
    const response = await api.post('/notices/draft', { document_id: documentId });
    setTaskId(response.data.task_id);
    notices.refetch();
  }

  function onDraftSuccess(data: unknown) {
    setResult(data as DraftResult);
    notices.refetch();
  }

  return <div className="space-y-5">
    <PageHeader title="Tax Notice Drafter" subtitle="Draft a context-grounded reply and verify every legal citation." />
    <div className="grid gap-4 rounded-xl border bg-white p-4 md:grid-cols-2">
      <div className="space-y-3"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><FileUploadZone clientId={clientId} docType="notice" onUploaded={setDocumentId} /></div>
      <div className="space-y-3"><button disabled={!documentId} onClick={draft} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">Generate reply draft</button><TaskStatusPoller taskId={taskId} onSuccess={onDraftSuccess} /></div>
    </div>
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">Ready drafts</p><p className="mt-1 text-2xl font-semibold text-gray-900">{readyCount}</p></div>
        <div className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">Queued or generating</p><p className="mt-1 text-2xl font-semibold text-gray-900">{activeCount}</p></div>
        <div className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">Failed drafts</p><p className="mt-1 text-2xl font-semibold text-gray-900">{failedCount}</p></div>
      </div>
      <div className="flex flex-wrap items-center gap-2 rounded-xl border bg-white p-3">
        <input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search notices, clients, OCR text" className="min-w-64 rounded-lg border px-3 py-2 text-sm" />
        <select value={listClientId} onChange={event => setListClientId(event.target.value)} className="rounded-lg border px-3 py-2 text-sm">
          <option value="">All clients</option>
          {(clients.data || []).map(client => <option key={client.id} value={client.id}>{client.name}</option>)}
        </select>
        {STATUS_OPTIONS.map(status => <button key={status} onClick={() => setStatusFilter(status)} className={`rounded-full px-3 py-1 text-xs font-medium ${statusFilter === status ? 'bg-gray-900 text-white' : 'bg-white text-gray-700 ring-1 ring-gray-200'}`}>{status.replaceAll('_', ' ')}</button>)}
      </div>
      <DataGrid rows={rows} columns={columns} pageSize={10} />
    </div>
    {result && <div className="space-y-4 rounded-xl border bg-white p-5">
      <div className="flex flex-wrap items-center gap-3">
        <StatusBadge value={result.validation?.valid ? 'verified' : 'review_required'} />
        <span className="text-xs text-gray-500">Provider: {result.provider || result.validation?.provider || 'unknown'}</span>
        <span className="text-xs text-gray-500">Confidence: {result.validation?.confidence || 'unknown'}</span>
      </div>
      {!result.validation?.valid && <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">CA review required. Unverified citations: {(result.validation?.unverified || []).join(', ') || 'none found; legal basis still needs review'}</div>}
      {result.notice_data && <div className="grid gap-3 rounded-lg bg-gray-50 p-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        {Object.entries(result.notice_data).filter(([key]) => key !== 'summary').map(([key, value]) => <div key={key}>
          <p className="text-xs uppercase tracking-wide text-gray-500">{key.replaceAll('_', ' ')}</p>
          <p className="font-medium text-gray-900">{value || '-'}</p>
        </div>)}
      </div>}
      <h2 className="font-medium text-gray-900">Draft reply</h2><pre className="whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm leading-6 text-gray-800">{result.draft}</pre>
      <details><summary className="cursor-pointer text-sm font-medium text-blue-700">Verified source chunks</summary><div className="mt-3 space-y-3">{(result.source_chunks || []).map((chunk, i) => <p key={i} className="rounded bg-gray-50 p-3 text-xs text-gray-600">{chunk}</p>)}</div></details>
    </div>}
    <AiSummaryModal
      artifactType="notice"
      artifact={aiTarget as unknown as Record<string, unknown> | null}
      open={!!aiTarget}
      onClose={() => setAiTarget(null)}
    />
  </div>;
}
