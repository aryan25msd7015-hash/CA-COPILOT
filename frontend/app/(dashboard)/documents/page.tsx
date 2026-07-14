'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { Download, Eye, FileText, RefreshCw, X } from 'lucide-react';
import { api } from '@/lib/api';
import { Client, DocumentPipeline, DocumentRecord, DocStatus } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import FileUploadZone from '@/components/shared/FileUploadZone';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

const DOC_TYPES = ['invoice', 'gstr2b', 'purchase_register', 'notice', 'trial_balance', 'bank_statement'];
const STATUSES: Array<DocStatus | ''> = [
  '',
  'pending_upload',
  'received',
  'pending',
  'processing',
  'ocr_complete',
  'failed_validation',
  'verified',
  'processed',
  'ocr_failed',
  'parse_failed',
];
const RETRYABLE_STATUSES: DocStatus[] = ['ocr_failed', 'parse_failed', 'failed_validation'];

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString('en-IN') : '-';
}

function toNumber(value?: number | string) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : undefined;
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function formatMoney(value?: number | string) {
  const amount = toNumber(value);
  return typeof amount === 'number' ? `INR ${amount.toLocaleString('en-IN')}` : '-';
}

export default function DocumentsPage() {
  const [clientId, setClientId] = useState('');
  const [docType, setDocType] = useState('invoice');
  const [filterClientId, setFilterClientId] = useState('');
  const [filterDocType, setFilterDocType] = useState('');
  const [filterStatus, setFilterStatus] = useState<DocStatus | ''>('');
  const [selected, setSelected] = useState<DocumentRecord | null>(null);
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const documents = useQuery<DocumentRecord[]>({
    queryKey: ['documents', filterClientId, filterDocType, filterStatus],
    queryFn: () => api.get('/documents', {
      params: {
        client_id: filterClientId || undefined,
        doc_type: filterDocType || undefined,
        status: filterStatus || undefined,
        limit: 500,
      },
    }).then(r => r.data),
  });
  const pipeline = useQuery<DocumentPipeline>({
    queryKey: ['document-pipeline', selected?.id],
    enabled: Boolean(selected?.id),
    queryFn: () => api.get(`/documents/${selected?.id}/pipeline`).then(r => r.data),
  });
  const clientNames = useMemo(() => Object.fromEntries((clients.data || []).map(client => [client.id, client.name])), [clients.data]);
  const latestExtraction = pipeline.data?.extractions?.[0];
  const selectedStatus = pipeline.data?.status || selected?.status;

  const retryDocument = useCallback(async (documentId: string) => {
    await api.post(`/documents/${documentId}/retry-ocr`);
    await documents.refetch();
    await pipeline.refetch();
  }, [documents, pipeline]);

  const downloadDocument = useCallback(async (documentId: string) => {
    try {
      const res = await api.get<{ download_url: string }>(`/documents/${documentId}/download-url`);
      if (res.data?.download_url) {
        window.open(res.data.download_url, '_blank');
      }
    } catch (e) {
      console.error('download failed', e);
      alert('Download failed — file may not be uploaded yet.');
    }
  }, []);

  const columns = useMemo<ColDef<DocumentRecord>[]>(() => [
    { field: 'original_filename', headerName: 'File', minWidth: 220, valueFormatter: p => String(p.value || '-') },
    { field: 'doc_type', headerName: 'Type' },
    { field: 'client_id', headerName: 'Client', valueFormatter: p => clientNames[String(p.value)] || String(p.value || '-') },
    { field: 'source', headerName: 'Source' },
    { field: 'status', headerName: 'Status', cellRenderer: (p: ICellRendererParams<DocumentRecord>) => <StatusBadge value={p.value} /> },
    { field: 'created_at', headerName: 'Created', valueFormatter: p => p.value ? new Date(p.value).toLocaleString('en-IN') : '-' },
    {
      headerName: 'Action',
      sortable: false,
      filter: false,
      minWidth: 180,
      cellRenderer: (p: ICellRendererParams<DocumentRecord>) => {
        const row = p.data;
        if (!row) return null;
        return (
          <div className="flex items-center gap-2">
            <button onClick={() => setSelected(row)} className="inline-flex items-center gap-1 text-xs font-medium text-blue-700">
              <Eye className="h-3.5 w-3.5" /> Details
            </button>
            {!(row as { seed?: boolean }).seed && (
              <button
                onClick={() => downloadDocument(row.id)}
                className="inline-flex items-center gap-1 text-xs font-medium text-slate-700"
                data-testid={`btn-download-${row.id}`}
              >
                <Download className="h-3.5 w-3.5" /> Download
              </button>
            )}
            {RETRYABLE_STATUSES.includes(row.status) && (
              <button onClick={() => retryDocument(row.id)} className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
                <RefreshCw className="h-3.5 w-3.5" /> Retry
              </button>
            )}
          </div>
        );
      },
    },
  ], [clientNames, retryDocument, downloadDocument]);

  return <div className="space-y-5">
    <PageHeader title="Documents" subtitle="Upload, process, and monitor client documents." />
    <div className="grid gap-4 rounded-xl border border-slate-200 bg-white/90 p-4 shadow-sm md:grid-cols-3">
      <ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} />
      <select value={docType} onChange={e => setDocType(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
        {DOC_TYPES.map(type => <option key={type}>{type}</option>)}
      </select>
      <FileUploadZone clientId={clientId} docType={docType} onUploaded={() => documents.refetch()} />
    </div>

    <div className="grid gap-3 rounded-xl border border-slate-200 bg-white/90 p-4 shadow-sm md:grid-cols-4">
      <ClientSelect clients={clients.data || []} value={filterClientId} onChange={setFilterClientId} />
      <select value={filterDocType} onChange={e => setFilterDocType(e.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
        <option value="">All document types</option>
        {DOC_TYPES.map(type => <option key={type} value={type}>{type}</option>)}
      </select>
      <select value={filterStatus} onChange={e => setFilterStatus(e.target.value as DocStatus | '')} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
        {STATUSES.map(status => <option key={status || 'all'} value={status}>{status ? status.replaceAll('_', ' ') : 'All statuses'}</option>)}
      </select>
      <button onClick={() => documents.refetch()} className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white">
        <RefreshCw className="h-4 w-4" /> Refresh list
      </button>
    </div>

    <DataGrid rows={documents.data || []} columns={columns} />

    {selected && (
      <div className="fixed inset-0 z-40 bg-slate-950/30 p-4 backdrop-blur-sm md:p-8">
        <div className="ml-auto flex h-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-start justify-between border-b border-slate-200 p-5">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-blue-600" />
                <h2 className="truncate text-lg font-semibold text-slate-950">{selected.original_filename || selected.doc_type}</h2>
              </div>
              <p className="mt-1 text-sm text-slate-500">{clientNames[selected.client_id] || selected.client_id}</p>
            </div>
            <div className="flex items-center gap-2">
              {selectedStatus && RETRYABLE_STATUSES.includes(selectedStatus) && (
                <button onClick={() => retryDocument(selected.id)} className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white">
                  <RefreshCw className="h-4 w-4" /> Retry OCR
                </button>
              )}
              <button onClick={() => setSelected(null)} className="rounded-full p-2 text-slate-500 hover:bg-slate-100" aria-label="Close document details">
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          <div className="flex-1 space-y-5 overflow-y-auto p-5">
            <div className="grid gap-3 md:grid-cols-4">
              {[
                ['Status', <StatusBadge key="status" value={pipeline.data?.status || selected.status} />],
                ['Type', selected.doc_type],
                ['Created', formatDate(selected.created_at)],
                ['Completed', formatDate(selected.processing_completed_at)],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
                  <div className="mt-1 text-sm font-semibold text-slate-900">{value}</div>
                </div>
              ))}
            </div>

            {pipeline.data?.last_pipeline_error_type && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                Pipeline issue: {pipeline.data.last_pipeline_error_type}
              </div>
            )}

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-950">Latest extraction</h3>
              {pipeline.isLoading && <p className="text-sm text-slate-500">Loading extraction details...</p>}
              {!pipeline.isLoading && !latestExtraction && <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">No extraction record yet.</p>}
              {latestExtraction && (
                <div className="grid gap-3 rounded-xl border border-slate-200 p-4 md:grid-cols-3">
                  <div><p className="text-xs text-slate-500">Supplier</p><p className="text-sm font-medium text-slate-900">{latestExtraction.supplier_name || '-'}</p></div>
                  <div><p className="text-xs text-slate-500">Invoice no.</p><p className="text-sm font-medium text-slate-900">{latestExtraction.invoice_number || '-'}</p></div>
                  <div><p className="text-xs text-slate-500">Confidence</p><p className="text-sm font-medium text-slate-900">{Math.round((toNumber(latestExtraction.confidence_score) || 0) * 100)}%</p></div>
                  <div><p className="text-xs text-slate-500">Taxable value</p><p className="text-sm font-medium text-slate-900">{formatMoney(latestExtraction.taxable_value)}</p></div>
                  <div><p className="text-xs text-slate-500">Total</p><p className="text-sm font-medium text-slate-900">{formatMoney(latestExtraction.total_amount)}</p></div>
                  <div><p className="text-xs text-slate-500">Validation</p><StatusBadge value={latestExtraction.validation_status} /></div>
                  <div className="md:col-span-3">
                    <p className="text-xs text-slate-500">Tags</p>
                    <div className="mt-1 flex flex-wrap gap-2">{(latestExtraction.auto_tags || []).map(tag => <span key={tag} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700">{tag}</span>)}</div>
                  </div>
                  {latestExtraction.validation_errors?.length > 0 && (
                    <div className="md:col-span-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
                      {latestExtraction.validation_errors.map((err, idx) => <p key={`${err.code}-${idx}`}>{err.code}: {err.message}</p>)}
                    </div>
                  )}
                </div>
              )}
            </section>

            <section className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-950">Pipeline timeline</h3>
              <div className="space-y-2">
                {(pipeline.data?.events || []).map(event => (
                  <div key={event.id} className="flex items-center justify-between rounded-xl border border-slate-200 p-3 text-sm">
                    <div>
                      <p className="font-medium text-slate-900">{event.stage.replaceAll('_', ' ')}</p>
                      <p className="text-xs text-slate-500">{formatDate(event.created_at)}</p>
                    </div>
                    <StatusBadge value={event.error_type || event.status} />
                  </div>
                ))}
                {!pipeline.isLoading && (pipeline.data?.events || []).length === 0 && <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">No pipeline events yet.</p>}
              </div>
            </section>
          </div>
        </div>
      </div>
    )}
  </div>;
}
