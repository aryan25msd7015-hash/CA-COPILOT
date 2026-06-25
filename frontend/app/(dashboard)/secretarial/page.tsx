'use client';

import { useCallback, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { downloadFromApi } from '@/lib/download';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface SecretarialType { id: string; title: string; xml_supported: boolean; }
interface SecretarialDoc { id: string; doc_type: string; doc_title: string; generated_text: string; has_xml: boolean; status: string; created_at: string; meeting_date?: string; resolution_count: number; director_count: number; compliance_flags: string[]; review_ready: boolean; word_count: number; }
interface Overview { total: number; draft: number; approved: number; review_required: number; xml_ready: number; flagged: number; approval_rate_pct: number; type_counts: Record<string, number>; }

export default function SecretarialPage() {
  const [clientId, setClientId] = useState('');
  const [docType, setDocType] = useState('board_minutes');
  const [transcript, setTranscript] = useState('');
  const [dataJson, setDataJson] = useState('{"meeting_type":"Board Meeting","venue":"Registered Office","chairman":"Ms. Priya Shah","directors_present":["Ms. Priya Shah","Mr. Karan Mehta"]}');
  const [preview, setPreview] = useState('');
  const [message, setMessage] = useState('');
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const types = useQuery<SecretarialType[]>({ queryKey: ['secretarial-types'], queryFn: () => api.get('/secretarial/types').then(r => r.data) });
  const records = useQuery<SecretarialDoc[]>({ queryKey: ['secretarial', clientId], queryFn: () => api.get(`/secretarial?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  const overview = useQuery<Overview>({ queryKey: ['secretarial-overview', clientId], queryFn: () => api.get(`/secretarial/overview?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  async function generate() {
    const response = await api.post('/secretarial', { client_id: clientId, doc_type: docType, transcript, data: JSON.parse(dataJson) });
    setPreview(response.data.generated_text); setMessage(`Generated ${response.data.doc_title}; ${response.data.compliance_flags.length} compliance flags.`);
    await Promise.all([records.refetch(), overview.refetch()]);
  }
  const approve = useCallback(async (row: SecretarialDoc) => {
    const response = await api.patch(`/secretarial/${row.id}`, { status: 'approved' });
    setMessage(`Document marked ${response.data.status}.`);
    await Promise.all([records.refetch(), overview.refetch()]);
  }, [records, overview]);
  const columns = useMemo<ColDef<SecretarialDoc>[]>(() => [
    { field: 'doc_title', headerName: 'Document type', minWidth: 190 },
    { field: 'status', headerName: 'Status', cellRenderer: (p: ICellRendererParams<SecretarialDoc>) => <StatusBadge value={p.value} /> },
    { field: 'meeting_date', headerName: 'Meeting date' }, { field: 'resolution_count', headerName: 'Resolutions' },
    { field: 'director_count', headerName: 'Directors' }, { field: 'word_count', headerName: 'Words' },
    { headerName: 'Flags', valueGetter: p => p.data?.compliance_flags?.length || 0 },
    { headerName: 'Actions', minWidth: 270, sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<SecretarialDoc>) => <div className="flex h-full items-center gap-3"><button onClick={() => p.data && setPreview(p.data.generated_text)} className="text-xs text-blue-700">Preview</button><button disabled={!p.data?.review_ready} onClick={() => p.data && approve(p.data)} className="text-xs text-gray-900 disabled:text-gray-300">Approve</button><button onClick={() => p.data && downloadFromApi(`/secretarial/${p.data.id}/export/docx`, `${p.data.doc_type}.docx`)} className="text-xs text-green-700">DOCX</button>{p.data?.has_xml && <button onClick={() => p.data && downloadFromApi(`/secretarial/${p.data.id}/export/xml`, `${p.data.doc_type}.xml`)} className="text-xs text-purple-700">XML</button>}</div> },
  ], [approve]);
  const metrics = [
    ['Documents', overview.data?.total || 0],
    ['Draft', overview.data?.draft || 0],
    ['Review required', overview.data?.review_required || 0],
    ['Approved', overview.data?.approved || 0],
    ['XML ready', overview.data?.xml_ready || 0],
    ['Flagged', overview.data?.flagged || 0],
    ['Approval rate', `${Number(overview.data?.approval_rate_pct || 0).toFixed(1)}%`],
    ['Types used', Object.keys(overview.data?.type_counts || {}).length],
  ];
  return <div className="space-y-5">
    <PageHeader title="MCA & Secretarial Documents" subtitle="Convert meeting transcripts into formal minutes, notices, and MCA filing data." />
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><select value={docType} onChange={e => setDocType(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">{(types.data || []).map(row => <option key={row.id} value={row.id}>{row.title}</option>)}</select><button disabled={!clientId || (!transcript && !['mgt7', 'aoc4'].includes(docType))} onClick={generate} className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Generate document</button></div>
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    <div className="grid gap-4 lg:grid-cols-2"><label className="text-sm font-medium">Meeting transcript<textarea value={transcript} onChange={e => setTranscript(e.target.value)} rows={10} placeholder="The board approved opening a new bank account. The directors authorized Ms. Priya Shah to sign..." className="mt-1 w-full rounded-xl border p-3 text-sm" /></label><label className="text-sm font-medium">Company / meeting data<textarea value={dataJson} onChange={e => setDataJson(e.target.value)} rows={10} className="mt-1 w-full rounded-xl border p-3 font-mono text-xs" /></label></div>
    {message && <p className="text-sm text-green-700">{message}</p>}
    {preview && <div className="rounded-xl border bg-white p-4"><h2 className="mb-2 text-sm font-semibold">Generated preview</h2><pre className="whitespace-pre-wrap text-sm text-gray-700">{preview}</pre></div>}
    <DataGrid rows={records.data || []} columns={columns} />
  </div>;
}
