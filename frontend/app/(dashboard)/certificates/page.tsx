'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { downloadFromApi } from '@/lib/download';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface CertType { id: string; title: string; fields: string[]; }
interface Certificate { id: string; cert_type: string; title: string; fields: Record<string, unknown>; validation: { valid: boolean; issues: unknown[]; missing_fields: string[] }; status: string; created_at: string; missing_count: number; issue_count: number; completeness_pct: number; export_ready: boolean; }
interface Overview { total: number; ready: number; review_required: number; approved: number; missing_fields: number; validation_issues: number; ready_rate_pct: number; type_counts: Record<string, number>; }

export default function CertificatesPage() {
  const [clientId, setClientId] = useState('');
  const [certType, setCertType] = useState('net_worth');
  const [sourceText, setSourceText] = useState('');
  const [fieldsJson, setFieldsJson] = useState('{}');
  const [referenceJson, setReferenceJson] = useState('{}');
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [referenceValues, setReferenceValues] = useState<Record<string, string>>({});
  const [editingId, setEditingId] = useState('');
  const [message, setMessage] = useState('');
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const types = useQuery<CertType[]>({ queryKey: ['certificate-types'], queryFn: () => api.get('/certificates/types').then(r => r.data) });
  const records = useQuery<Certificate[]>({ queryKey: ['certificates', clientId], queryFn: () => api.get(`/certificates?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  const overview = useQuery<Overview>({ queryKey: ['certificate-overview', clientId], queryFn: () => api.get(`/certificates/overview?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  const selectedType = types.data?.find(row => row.id === certType);
  function parsedPayload() {
    const manualFields = Object.fromEntries(Object.entries(fieldValues).filter(([, value]) => value !== '').map(([key, value]) => [key, Number.isNaN(Number(value)) ? value : Number(value)]));
    const reference = Object.fromEntries(Object.entries(referenceValues).filter(([, value]) => value !== '').map(([key, value]) => [key, Number(value)]));
    return {
      fields: { ...manualFields, ...JSON.parse(fieldsJson || '{}') },
      reference_values: { ...reference, ...JSON.parse(referenceJson || '{}') },
    };
  }
  async function generate() {
    const payload = parsedPayload();
    const response = await api.post('/certificates', { client_id: clientId, cert_type: certType, source_text: sourceText, ...payload });
    await Promise.all([records.refetch(), overview.refetch()]); setMessage(`Certificate generated with status: ${response.data.status}; completeness ${response.data.completeness_pct}%.`);
  }
  async function update() {
    const payload = parsedPayload();
    const response = await api.patch(`/certificates/${editingId}`, { ...payload, status: 'ready' });
    await Promise.all([records.refetch(), overview.refetch()]); setMessage(`Certificate fields reviewed and saved. Missing ${response.data.missing_count}, issues ${response.data.issue_count}.`);
  }
  const columns = useMemo<ColDef<Certificate>[]>(() => [
    { field: 'title', headerName: 'Certificate', minWidth: 220 }, { field: 'status', headerName: 'Status', cellRenderer: (p: ICellRendererParams<Certificate>) => <StatusBadge value={p.value} /> },
    { field: 'completeness_pct', headerName: 'Complete', valueFormatter: p => `${Number(p.value || 0).toFixed(1)}%` },
    { field: 'missing_count', headerName: 'Missing' }, { field: 'issue_count', headerName: 'Issues' }, { field: 'created_at', headerName: 'Created' },
    { headerName: 'Actions', minWidth: 180, sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<Certificate>) => <div className="flex h-full items-center gap-3"><button onClick={() => { if (p.data) { setEditingId(p.data.id); setFieldsJson(JSON.stringify(p.data.fields, null, 2)); setFieldValues(Object.fromEntries(Object.entries(p.data.fields || {}).map(([key, value]) => [key, String(value ?? '')]))); setCertType(p.data.cert_type); } }} className="text-xs text-blue-700">Review fields</button><button onClick={() => p.data && downloadFromApi(`/certificates/${p.data.id}/export`, `${p.data.cert_type}-certificate.docx`)} className="text-xs text-green-700">DOCX</button></div> },
  ], []);
  const metrics = [
    ['Certificates', overview.data?.total || 0],
    ['Ready', overview.data?.ready || 0],
    ['Review required', overview.data?.review_required || 0],
    ['Approved', overview.data?.approved || 0],
    ['Missing fields', overview.data?.missing_fields || 0],
    ['Validation issues', overview.data?.validation_issues || 0],
    ['Ready rate', `${Number(overview.data?.ready_rate_pct || 0).toFixed(1)}%`],
    ['Types used', Object.keys(overview.data?.type_counts || {}).length],
  ];
  return <div className="space-y-5">
    <PageHeader title="CA Certificate Generator" subtitle="Extract, cross-check, review, and export signed-ready ICAI-style certificates." />
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><select value={certType} onChange={e => { setCertType(e.target.value); setFieldValues({}); setReferenceValues({}); }} className="rounded-lg border px-3 py-2 text-sm">{(types.data || []).map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select><button disabled={!clientId} onClick={editingId ? update : generate} className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">{editingId ? 'Save reviewed fields' : 'Generate certificate'}</button>{editingId && <button onClick={() => { setEditingId(''); setFieldsJson('{}'); setFieldValues({}); }} className="rounded-lg border px-3 py-2 text-sm">New certificate</button>}</div>
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    <div className="grid gap-4 lg:grid-cols-3"><label className="text-sm font-medium">Source document text<textarea value={sourceText} onChange={e => setSourceText(e.target.value)} rows={12} placeholder="Paste OCR text such as Net worth FY1: 4500000" className="mt-1 w-full rounded-xl border p-3 text-sm" /></label><div className="rounded-xl border bg-white p-4 lg:col-span-2"><p className="mb-3 text-sm font-medium">Review fields</p><div className="grid gap-3 md:grid-cols-2">{(selectedType?.fields || []).map(field => <div key={field} className="grid gap-1"><label className="text-xs text-gray-500">{field.replaceAll('_', ' ')}</label><input value={fieldValues[field] || ''} onChange={e => setFieldValues({ ...fieldValues, [field]: e.target.value })} className="rounded border px-3 py-2 text-sm" placeholder="Certificate value" /><input value={referenceValues[field] || ''} onChange={e => setReferenceValues({ ...referenceValues, [field]: e.target.value })} className="rounded border px-3 py-2 text-xs" placeholder="Official reference value" /></div>)}</div></div></div>
    <div className="grid gap-4 lg:grid-cols-2"><label className="text-sm font-medium">Manual JSON overrides<textarea value={fieldsJson} onChange={e => setFieldsJson(e.target.value)} rows={6} className="mt-1 w-full rounded-xl border p-3 font-mono text-xs" /></label><label className="text-sm font-medium">Reference JSON overrides<textarea value={referenceJson} onChange={e => setReferenceJson(e.target.value)} rows={6} placeholder='{"turnover_fy1": 8500000}' className="mt-1 w-full rounded-xl border p-3 font-mono text-xs" /></label></div>
    <p className="text-xs text-gray-500">Required fields: {(types.data?.find(row => row.id === certType)?.fields || []).join(', ')}</p>
    {message && <p className="text-sm text-green-700">{message}</p>}
    <DataGrid rows={records.data || []} columns={columns} />
  </div>;
}
