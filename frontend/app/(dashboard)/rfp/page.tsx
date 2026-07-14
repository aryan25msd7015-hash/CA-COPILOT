'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { downloadFromApi } from '@/lib/download';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface Bid { id: string; title: string; eligibility: { overall_eligible: boolean; criteria: unknown[]; disqualifying_gaps: string[] }; proposal_text?: string; status: string; created_at: string; criteria_count: number; passed_count: number; gap_count: number; eligibility_score: number; proposal_ready: boolean; rfp_excerpt: string; }
interface Overview { total_bids: number; generated: number; ineligible: number; approved: number; rejected: number; proposal_ready: number; average_score: number; credential_health: { score: number; missing: string[] }; }
const initialCredentials = {
  firm_name: '', icai_regn_no: '', founding_year: 2010, hq_city: '', hq_state: '',
  partners: '[{"name":"Aarav Mehta","membership_no":"123456","experience_years":18,"specializations":["Statutory Audit"]}]',
  article_clerks: 10, total_staff: 25, gross_fee_receipts_fy1: 12000000, gross_fee_receipts_fy2: 10500000, gross_fee_receipts_fy3: 9000000,
  industries_served: '[{"industry":"Manufacturing","client_count":12,"years":10}]',
  key_engagements: '[{"name":"Manufacturing statutory audit"}]', peer_review_status: 'valid', quality_review_date: '',
};

export default function RfpPage() {
  const [credentials, setCredentials] = useState(initialCredentials);
  const [title, setTitle] = useState('');
  const [rfpText, setRfpText] = useState('');
  const [preview, setPreview] = useState('');
  const [message, setMessage] = useState('');
  const saved = useQuery<Record<string, unknown> | null>({ queryKey: ['rfp-credentials'], queryFn: () => api.get('/rfp/credentials').then(r => r.data) });
  const bids = useQuery<Bid[]>({ queryKey: ['rfp-bids'], queryFn: () => api.get('/rfp/bids').then(r => r.data) });
  const overview = useQuery<Overview>({ queryKey: ['rfp-overview'], queryFn: () => api.get('/rfp/overview').then(r => r.data) });
  useEffect(() => {
    const data = saved.data;
    if (!data) return;
    setCredentials(current => ({
      ...current,
      ...(data as Partial<typeof initialCredentials>),
      partners: JSON.stringify(data.partners || [], null, 2),
      industries_served: JSON.stringify(data.industries_served || [], null, 2),
      key_engagements: JSON.stringify(data.key_engagements || [], null, 2),
      quality_review_date: String(data.quality_review_date || ''),
    }));
  }, [saved.data]);
  async function saveCredentials() {
    await api.put('/rfp/credentials', { ...credentials, founding_year: Number(credentials.founding_year), article_clerks: Number(credentials.article_clerks), total_staff: Number(credentials.total_staff), gross_fee_receipts_fy1: Number(credentials.gross_fee_receipts_fy1), gross_fee_receipts_fy2: Number(credentials.gross_fee_receipts_fy2), gross_fee_receipts_fy3: Number(credentials.gross_fee_receipts_fy3), quality_review_date: credentials.quality_review_date || null, partners: JSON.parse(credentials.partners), industries_served: JSON.parse(credentials.industries_served), key_engagements: JSON.parse(credentials.key_engagements) });
    await Promise.all([saved.refetch(), overview.refetch()]);
    setMessage('Reusable firm credential profile saved.');
  }
  async function analyze() {
    const response = await api.post('/rfp/bids', { title, rfp_text: rfpText });
    setPreview(`ELIGIBILITY CHECK\n${JSON.stringify(response.data.eligibility, null, 2)}\n\n${response.data.proposal_text || 'No proposal generated because one or more eligibility criteria failed.'}`);
    await Promise.all([bids.refetch(), overview.refetch()]); setMessage(`RFP analysis complete: ${response.data.status}; score ${response.data.eligibility_score}%.`);
  }
  const setBidStatus = useCallback(async (row: Bid, status: string) => {
    const response = await api.patch(`/rfp/bids/${row.id}`, { status });
    setMessage(`${row.title} marked ${response.data.status}.`);
    await Promise.all([bids.refetch(), overview.refetch()]);
  }, [bids, overview]);
  const columns = useMemo<ColDef<Bid>[]>(() => [
    { field: 'title', headerName: 'RFP', minWidth: 220 }, { field: 'status', headerName: 'Status', cellRenderer: (p: ICellRendererParams<Bid>) => <StatusBadge value={p.value} /> },
    { field: 'eligibility_score', headerName: 'Score', valueFormatter: p => `${Number(p.value || 0).toFixed(1)}%` },
    { field: 'criteria_count', headerName: 'Criteria' }, { field: 'gap_count', headerName: 'Gaps' },
    { field: 'created_at', headerName: 'Created' }, { headerName: 'Actions', minWidth: 260, sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<Bid>) => <div className="flex h-full items-center gap-3"><button onClick={() => p.data && setPreview(`ELIGIBILITY CHECK\nScore: ${p.data.eligibility_score}%\n${JSON.stringify(p.data.eligibility, null, 2)}\n\n${p.data.proposal_text || 'No proposal generated because one or more eligibility criteria failed.'}`)} className="text-xs text-blue-700">Preview</button>{p.data?.proposal_text && <button onClick={() => p.data && setBidStatus(p.data, 'approved')} className="text-xs text-gray-900">Approve</button>}<button onClick={() => p.data && setBidStatus(p.data, 'rejected')} className="text-xs text-red-700">Reject</button>{p.data?.proposal_text && <button onClick={() => p.data && downloadFromApi(`/rfp/bids/${p.data.id}/export`, `technical-bid-${p.data.id}.docx`)} className="text-xs text-green-700">DOCX</button>}</div> },
  ], [setBidStatus]);
  const metrics = [
    ['Bids', overview.data?.total_bids || 0],
    ['Generated', overview.data?.generated || 0],
    ['Approved', overview.data?.approved || 0],
    ['Ineligible', overview.data?.ineligible || 0],
    ['Rejected', overview.data?.rejected || 0],
    ['Proposal ready', overview.data?.proposal_ready || 0],
    ['Avg score', `${Number(overview.data?.average_score || 0).toFixed(1)}%`],
    ['Credential health', `${Number(overview.data?.credential_health?.score || 0).toFixed(1)}%`],
  ];
  const simpleFields = ['firm_name', 'icai_regn_no', 'founding_year', 'hq_city', 'hq_state', 'article_clerks', 'total_staff', 'gross_fee_receipts_fy1', 'gross_fee_receipts_fy2', 'gross_fee_receipts_fy3', 'peer_review_status', 'quality_review_date'] as const;
  return <div className="space-y-5">
    <PageHeader title="Audit Bid & RFP Generator" subtitle="Check eligibility against stored credentials and generate evidence-backed technical bids." />
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    {!!overview.data?.credential_health?.missing?.length && <div className="rounded-xl border bg-amber-50 p-4 text-sm text-amber-800">Credential gaps: {overview.data.credential_health.missing.join(', ')}</div>}
    <div className="rounded-xl border bg-white p-4"><h2 className="mb-3 text-sm font-semibold">Firm credentials</h2><div className="grid gap-3 md:grid-cols-4">{simpleFields.map(key => <input key={key} value={credentials[key]} onChange={e => setCredentials({ ...credentials, [key]: e.target.value })} placeholder={key.replaceAll('_', ' ')} className="rounded border px-3 py-2 text-sm" />)}</div><div className="mt-3 grid gap-3 lg:grid-cols-3"><textarea value={credentials.partners} onChange={e => setCredentials({ ...credentials, partners: e.target.value })} rows={6} className="rounded border p-3 font-mono text-xs" /><textarea value={credentials.industries_served} onChange={e => setCredentials({ ...credentials, industries_served: e.target.value })} rows={6} className="rounded border p-3 font-mono text-xs" /><textarea value={credentials.key_engagements} onChange={e => setCredentials({ ...credentials, key_engagements: e.target.value })} rows={6} className="rounded border p-3 font-mono text-xs" /></div><button onClick={saveCredentials} className="mt-3 rounded bg-gray-900 px-3 py-2 text-sm text-white">Save credential database</button></div>
    <div className="grid gap-4 lg:grid-cols-[260px_1fr]"><div className="space-y-3"><input value={title} onChange={e => setTitle(e.target.value)} placeholder="RFP title" className="w-full rounded border px-3 py-2 text-sm" /><button disabled={!title || !rfpText} onClick={analyze} className="w-full rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Check eligibility & generate bid</button>{message && <p className="text-sm text-green-700">{message}</p>}</div><textarea value={rfpText} onChange={e => setRfpText(e.target.value)} rows={10} placeholder="Paste RFP eligibility and scope text..." className="rounded-xl border p-3 text-sm" /></div>
    {preview && <div className="rounded-xl border bg-white p-4"><pre className="whitespace-pre-wrap text-sm">{preview}</pre></div>}
    <DataGrid rows={bids.data || []} columns={columns} />
  </div>;
}
