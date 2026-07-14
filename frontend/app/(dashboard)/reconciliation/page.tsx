'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, RefreshCw } from 'lucide-react';
import { api } from '@/lib/api';
import { Client, MatchStatus, ReconciliationResult, TransactionRecord } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import PageHeader from '@/components/shared/PageHeader';
import ReconciliationGrid from '@/components/reconciliation/ReconciliationGrid';
import StatusBadge from '@/components/shared/StatusBadge';

function formatMoney(value?: number) {
  return typeof value === 'number' ? `INR ${value.toLocaleString('en-IN')}` : '-';
}

function formatDate(value?: string) {
  return value ? new Date(value).toLocaleString('en-IN') : '-';
}

export default function ReconciliationPage() {
  const [clientId, setClientId] = useState('');
  const [unmatchedOnly, setUnmatchedOnly] = useState(false);
  const [transactionSource, setTransactionSource] = useState('');
  const [transactionStatus, setTransactionStatus] = useState<MatchStatus | ''>('');
  const [transactionPeriod, setTransactionPeriod] = useState(new Date().toISOString().slice(0, 7));
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const txns = useQuery<TransactionRecord[]>({
    queryKey: ['transactions', clientId, unmatchedOnly, transactionSource, transactionStatus, transactionPeriod],
    queryFn: () => api.get('/reconciliation/transactions', {
      params: {
        client_id: clientId,
        match_status: unmatchedOnly ? 'unmatched' : transactionStatus || undefined,
        source: transactionSource || undefined,
        period: transactionPeriod || undefined,
        limit: 5000,
      },
    }).then(r => r.data),
    enabled: !!clientId,
  });
  const results = useQuery<ReconciliationResult[]>({ queryKey: ['reconciliation-results', clientId], queryFn: () => api.get(`/reconciliation/results/${clientId}`).then(r => r.data), enabled: !!clientId });

  async function downloadExport(resultId: string) {
    const response = await api.get(`/reconciliation/export/${resultId}`, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `reconciliation-${resultId}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  }

  return <div className="space-y-5">
    <PageHeader title="GST Reconciliation" subtitle="Match purchase records against GSTR-2B and review exceptions." actions={<label className="text-sm text-gray-600"><input type="checkbox" checked={unmatchedOnly} onChange={e => setUnmatchedOnly(e.target.checked)} className="mr-2" />Unmatched only</label>} />
    <ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} />
    <div className="grid gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-4">
      <label className="text-xs font-medium text-slate-600">Period
        <input type="month" value={transactionPeriod} onChange={e => setTransactionPeriod(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 text-sm" />
      </label>
      <label className="text-xs font-medium text-slate-600">Source
        <select value={transactionSource} onChange={e => setTransactionSource(e.target.value)} className="mt-1 w-full rounded-lg border px-3 py-2 text-sm">
          <option value="">All sources</option>
          <option value="upload">Purchase register</option>
          <option value="gstr2b">GSTR-2B</option>
        </select>
      </label>
      <label className="text-xs font-medium text-slate-600">Match status
        <select value={transactionStatus} disabled={unmatchedOnly} onChange={e => setTransactionStatus(e.target.value as MatchStatus | '')} className="mt-1 w-full rounded-lg border px-3 py-2 text-sm disabled:bg-slate-100">
          <option value="">All statuses</option>
          <option value="exact">Exact</option>
          <option value="tolerance">Tolerance</option>
          <option value="fuzzy">Fuzzy</option>
          <option value="unmatched">Unmatched</option>
        </select>
      </label>
      <div>
        <p className="text-xs font-medium uppercase text-slate-500">Transactions</p>
        <p className="mt-2 text-2xl font-semibold text-slate-950">{txns.data?.length ?? 0}</p>
      </div>
    </div>
    <ReconciliationGrid clientId={clientId} rows={txns.data || []} resultId={results.data?.[0]?.id} onComplete={() => { txns.refetch(); results.refetch(); }} />
    {clientId && (
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-950">Reconciliation results</h2>
            <p className="text-xs text-slate-500">Recent runs for the selected client.</p>
          </div>
          <button onClick={() => results.refetch()} className="inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium text-slate-700">
            <RefreshCw className="h-4 w-4" /> Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] border-separate border-spacing-0 text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="border-b border-slate-200 px-3 py-2">Period</th>
                <th className="border-b border-slate-200 px-3 py-2">Status</th>
                <th className="border-b border-slate-200 px-3 py-2">Purchase</th>
                <th className="border-b border-slate-200 px-3 py-2">GSTR-2B</th>
                <th className="border-b border-slate-200 px-3 py-2">Matched</th>
                <th className="border-b border-slate-200 px-3 py-2">Unmatched</th>
                <th className="border-b border-slate-200 px-3 py-2">Variance</th>
                <th className="border-b border-slate-200 px-3 py-2">Run at</th>
                <th className="border-b border-slate-200 px-3 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {(results.data || []).map(result => (
                <tr key={result.id} className="text-slate-700">
                  <td className="border-b border-slate-100 px-3 py-3 font-medium text-slate-950">{result.period}</td>
                  <td className="border-b border-slate-100 px-3 py-3"><StatusBadge value={result.status} /></td>
                  <td className="border-b border-slate-100 px-3 py-3">{formatMoney(result.total_purchase)}</td>
                  <td className="border-b border-slate-100 px-3 py-3">{formatMoney(result.total_gstr2b)}</td>
                  <td className="border-b border-slate-100 px-3 py-3">{result.matched_count ?? '-'}</td>
                  <td className="border-b border-slate-100 px-3 py-3">{result.unmatched_count ?? '-'}</td>
                  <td className="border-b border-slate-100 px-3 py-3">{formatMoney(result.mismatch_value)}</td>
                  <td className="border-b border-slate-100 px-3 py-3">{formatDate(result.completed_at || result.run_at)}</td>
                  <td className="border-b border-slate-100 px-3 py-3">
                    <button disabled={result.status !== 'completed'} onClick={() => downloadExport(result.id)} className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 disabled:text-slate-400">
                      <Download className="h-3.5 w-3.5" /> Export
                    </button>
                  </td>
                </tr>
              ))}
              {!results.isLoading && (results.data || []).length === 0 && (
                <tr><td colSpan={9} className="px-3 py-6 text-center text-sm text-slate-500">No reconciliation results yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    )}
  </div>;
}
