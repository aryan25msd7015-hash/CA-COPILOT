'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { ReconciliationConfig, ReconciliationMatchAction, ReconciliationResult, TransactionRecord } from '@/types';
import DataGrid from '@/components/shared/DataGrid';
import StatusBadge from '@/components/shared/StatusBadge';
import TaskStatusPoller from '@/components/shared/TaskStatusPoller';
import { usePermission } from '@/hooks/usePermission';

const CONFIG_PRESETS = {
  strict: { amount_tolerance: 1, date_tolerance: 0, fuzzy_threshold: 95 },
  standard: { amount_tolerance: 5, date_tolerance: 3, fuzzy_threshold: 85 },
  loose: { amount_tolerance: 25, date_tolerance: 7, fuzzy_threshold: 75 },
};

export default function ReconciliationGrid({ clientId, rows, resultId, onComplete }: {
  clientId: string;
  rows: TransactionRecord[];
  resultId?: string;
  onComplete: () => void;
}) {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [runMessage, setRunMessage] = useState('');
  const [runSummary, setRunSummary] = useState<Record<string, number> | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [form, setForm] = useState({ amount_tolerance: 5, date_tolerance: 3, fuzzy_threshold: 85 });
  const [saveMessage, setSaveMessage] = useState('');
  const [manualPurchaseId, setManualPurchaseId] = useState('');
  const [manualGstr2bId, setManualGstr2bId] = useState('');
  const [manualReason, setManualReason] = useState('');
  const [manualMessage, setManualMessage] = useState('');
  const canExport = usePermission('export:reconciliation');
  const config = useQuery<ReconciliationConfig>({
    queryKey: ['reconciliation-config', clientId],
    queryFn: () => api.get(`/reconciliation/config/${clientId}`).then(r => r.data),
    enabled: !!clientId,
  });
  const latestResult = useQuery<ReconciliationResult | null>({
    queryKey: ['reconciliation-latest-result', clientId],
    queryFn: () => api.get(`/reconciliation/results/${clientId}`, { params: { limit: 1 } }).then(r => r.data?.[0] || null),
    enabled: !!clientId,
  });
  const actions = useQuery<ReconciliationMatchAction[]>({
    queryKey: ['reconciliation-actions', clientId],
    queryFn: () => api.get('/reconciliation/actions', { params: { client_id: clientId, limit: 10 } }).then(r => r.data),
    enabled: !!clientId,
  });

  useEffect(() => {
    if (config.data) {
      setForm({
        amount_tolerance: Number(config.data.amount_tolerance),
        date_tolerance: Number(config.data.date_tolerance),
        fuzzy_threshold: Number(config.data.fuzzy_threshold),
      });
    }
  }, [config.data]);

  const summary = useMemo(() => rows.reduce((acc, row) => {
    acc.total += Number(row.amount || 0);
    acc[row.match_status] = (acc[row.match_status] || 0) + 1;
    if (row.source === 'upload') acc.purchase += 1;
    if (row.source === 'gstr2b') acc.gstr2b += 1;
    return acc;
  }, { total: 0, exact: 0, tolerance: 0, fuzzy: 0, unmatched: 0, purchase: 0, gstr2b: 0 } as Record<string, number>), [rows]);

  const columns = useMemo<ColDef<TransactionRecord>[]>(() => [
    { field: 'invoice_no', headerName: 'Invoice' },
    {
      field: 'source',
      headerName: 'Source',
      minWidth: 135,
      cellRenderer: (p: ICellRendererParams<TransactionRecord>) => <StatusBadge value={p.value === 'upload' ? 'purchase' : p.value} />,
    },
    { field: 'vendor_name', headerName: 'Vendor', minWidth: 180 },
    { field: 'vendor_gstin', headerName: 'GSTIN', minWidth: 165 },
    {
      field: 'amount',
      headerName: 'Amount',
      valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}`,
    },
    { field: 'date', headerName: 'Date' },
    {
      field: 'match_status',
      headerName: 'Match',
      cellRenderer: (p: ICellRendererParams<TransactionRecord>) => <StatusBadge value={p.value} />,
    },
    {
      field: 'match_confidence',
      headerName: 'Confidence',
      valueFormatter: p => p.value == null ? '-' : `${Number(p.value).toFixed(0)}%`,
    },
    {
      field: 'anomaly_score',
      headerName: 'Risk',
      valueFormatter: p => p.value == null ? '-' : `${Math.round(Number(p.value) * 100)}%`,
      cellClassRules: { 'text-red-700 font-semibold': p => Number(p.value || 0) >= 0.7 },
    },
    { field: 'document_id', headerName: 'Document', valueFormatter: p => p.value ? String(p.value).slice(0, 8) : '-' },
  ], []);

  async function run() {
    const response = await api.post('/reconciliation/run', { client_id: clientId, period });
    setTaskId(response.data.task_id);
    setRunMessage(response.data.message || 'Reconciliation queued.');
    setRunSummary(response.data.input_summary || null);
    await latestResult.refetch();
  }

  async function saveSettings() {
    await api.put(`/reconciliation/config/${clientId}`, form);
    await config.refetch();
    setSaveMessage('Tolerance settings saved.');
  }

  function applyPreset(name: keyof typeof CONFIG_PRESETS) {
    setForm(CONFIG_PRESETS[name]);
    setSaveMessage('');
  }

  const configValid = form.amount_tolerance >= 0 && form.amount_tolerance <= 100000
    && form.date_tolerance >= 0 && form.date_tolerance <= 90
    && form.fuzzy_threshold >= 0 && form.fuzzy_threshold <= 100;

  async function downloadExport() {
    if (!resultId) return;
    const response = await api.get(`/reconciliation/export/${resultId}`, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `reconciliation-${resultId}.xlsx`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function applyManualMatch() {
    await api.post('/reconciliation/manual-match', {
      purchase_transaction_id: manualPurchaseId,
      gstr2b_transaction_id: manualGstr2bId || undefined,
      result_id: resultId,
      reason: manualReason,
      confidence: 100,
    });
    setManualMessage('Manual match recorded.');
    setManualReason('');
    await actions.refetch();
    onComplete();
  }

  async function applyUnmatch() {
    await api.post('/reconciliation/unmatch', {
      purchase_transaction_id: manualPurchaseId,
      result_id: resultId,
      reason: manualReason,
    });
    setManualMessage('Transaction marked unmatched.');
    setManualReason('');
    await actions.refetch();
    onComplete();
  }

  async function rollbackAction(actionId: string) {
    await api.post(`/reconciliation/actions/${actionId}/rollback`);
    setManualMessage('Action rolled back.');
    await actions.refetch();
    onComplete();
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-xs font-medium text-gray-600">Period
          <input type="month" value={period} onChange={e => setPeriod(e.target.value)} className="ml-2 rounded-lg border px-3 py-2 text-sm" />
        </label>
        <button disabled={!clientId || !period} onClick={run} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
          Run reconciliation
        </button>
        <button disabled={!clientId} onClick={() => setSettingsOpen(value => !value)} className="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-50">
          Tolerance settings
        </button>
        {canExport && resultId && (
          <button onClick={downloadExport} className="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700">Export Excel</button>
        )}
        <TaskStatusPoller taskId={taskId} onSuccess={onComplete} />
      </div>

      {(runMessage || latestResult.data) && (
        <div className="grid gap-3 rounded-xl border bg-white p-4 md:grid-cols-4">
          <div>
            <p className="text-xs font-medium uppercase text-gray-500">Latest run</p>
            <div className="mt-1"><StatusBadge value={latestResult.data?.status || (taskId ? 'queued' : 'pending')} /></div>
          </div>
          <div>
            <p className="text-xs font-medium uppercase text-gray-500">Purchase rows</p>
            <p className="mt-1 text-lg font-semibold text-gray-900">{runSummary?.purchase_count ?? latestResult.data?.input_summary?.purchase_count ?? '-'}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase text-gray-500">GSTR-2B rows</p>
            <p className="mt-1 text-lg font-semibold text-gray-900">{runSummary?.gstr2b_count ?? latestResult.data?.input_summary?.gstr2b_count ?? '-'}</p>
          </div>
          <div>
            <p className="text-xs font-medium uppercase text-gray-500">Message</p>
            <p className="mt-1 text-sm text-gray-700">{runMessage || latestResult.data?.error_message || latestResult.data?.period || '-'}</p>
          </div>
        </div>
      )}

      {settingsOpen && clientId && (
        <div className="space-y-4 rounded-xl border bg-white p-4">
          <div className="flex flex-wrap items-center gap-2">
            {(['strict', 'standard', 'loose'] as const).map(name => (
              <button key={name} onClick={() => applyPreset(name)} className="rounded-lg border px-3 py-2 text-xs font-medium capitalize text-gray-700">
                {name}
              </button>
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-4">
            <label className="text-xs text-gray-600">Amount tolerance
              <input type="number" min={0} max={100000} step={0.01} value={form.amount_tolerance} onChange={e => setForm({ ...form, amount_tolerance: Number(e.target.value) })} className="mt-1 w-full rounded border px-3 py-2 text-sm" />
              <span className="mt-1 block text-[11px] text-gray-500">Allowed variance per invoice amount.</span>
            </label>
            <label className="text-xs text-gray-600">Date tolerance (days)
              <input type="number" min={0} max={90} value={form.date_tolerance} onChange={e => setForm({ ...form, date_tolerance: Number(e.target.value) })} className="mt-1 w-full rounded border px-3 py-2 text-sm" />
              <span className="mt-1 block text-[11px] text-gray-500">Used for tolerance matches after GSTIN/invoice checks.</span>
            </label>
            <label className="text-xs text-gray-600">Fuzzy threshold (%)
              <input type="number" min={0} max={100} value={form.fuzzy_threshold} onChange={e => setForm({ ...form, fuzzy_threshold: Number(e.target.value) })} className="mt-1 w-full rounded border px-3 py-2 text-sm" />
              <span className="mt-1 block text-[11px] text-gray-500">Minimum vendor-name similarity for fuzzy matches.</span>
            </label>
            <div className="flex items-end gap-2">
              <button disabled={!configValid} onClick={saveSettings} className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50">Save settings</button>
              <button onClick={() => applyPreset('standard')} className="rounded border px-3 py-2 text-sm text-gray-700">Reset</button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            {!configValid && <span className="text-red-700">Settings are outside allowed bounds.</span>}
            {saveMessage && <span className="text-green-700">{saveMessage}</span>}
            <span className="text-gray-500">Current: INR {form.amount_tolerance} / {form.date_tolerance} day(s) / {form.fuzzy_threshold}% fuzzy.</span>
          </div>
        </div>
      )}

      <div className="grid gap-3 rounded-xl border bg-white p-4 md:grid-cols-6">
        {[
          ['Total value', `INR ${summary.total.toLocaleString('en-IN')}`],
          ['Purchase rows', summary.purchase],
          ['GSTR-2B rows', summary.gstr2b],
          ['Exact', summary.exact],
          ['Tolerance/Fuzzy', summary.tolerance + summary.fuzzy],
          ['Unmatched', summary.unmatched],
        ].map(([label, value]) => (
          <div key={String(label)}>
            <p className="text-xs font-medium uppercase text-gray-500">{label}</p>
            <p className="mt-1 text-lg font-semibold text-gray-900">{value}</p>
          </div>
        ))}
      </div>

      {clientId && (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-950">Manual match cockpit</h2>
            <p className="text-xs text-slate-500">Override a purchase transaction match with reasoned audit history.</p>
          </div>
          <div className="grid gap-3 md:grid-cols-[1fr_1fr_1.4fr_auto_auto]">
            <select value={manualPurchaseId} onChange={e => setManualPurchaseId(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
              <option value="">Purchase transaction</option>
              {rows.filter(row => row.source === 'upload').map(row => (
                <option key={row.id} value={row.id}>{row.invoice_no || row.id.slice(0, 8)} - INR {Number(row.amount || 0).toLocaleString('en-IN')}</option>
              ))}
            </select>
            <select value={manualGstr2bId} onChange={e => setManualGstr2bId(e.target.value)} className="rounded-lg border px-3 py-2 text-sm">
              <option value="">GSTR-2B transaction</option>
              {rows.filter(row => row.source === 'gstr2b').map(row => (
                <option key={row.id} value={row.id}>{row.invoice_no || row.id.slice(0, 8)} - INR {Number(row.amount || 0).toLocaleString('en-IN')}</option>
              ))}
            </select>
            <input value={manualReason} onChange={e => setManualReason(e.target.value)} className="rounded-lg border px-3 py-2 text-sm" placeholder="Reason for override" />
            <button disabled={!manualPurchaseId || !manualReason || manualReason.length < 3} onClick={applyManualMatch} className="rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
              Match
            </button>
            <button disabled={!manualPurchaseId || !manualReason || manualReason.length < 3} onClick={applyUnmatch} className="rounded-lg border px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-50">
              Unmatch
            </button>
          </div>
          {manualMessage && <p className="text-xs text-green-700">{manualMessage}</p>}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-500">
                  <th className="border-b px-3 py-2">Action</th>
                  <th className="border-b px-3 py-2">Previous</th>
                  <th className="border-b px-3 py-2">New</th>
                  <th className="border-b px-3 py-2">Reason</th>
                  <th className="border-b px-3 py-2">Created</th>
                  <th className="border-b px-3 py-2">Rollback</th>
                </tr>
              </thead>
              <tbody>
                {(actions.data || []).map(action => (
                  <tr key={action.id}>
                    <td className="border-b border-slate-100 px-3 py-2"><StatusBadge value={action.action_type} /></td>
                    <td className="border-b border-slate-100 px-3 py-2">{action.previous_status || '-'}</td>
                    <td className="border-b border-slate-100 px-3 py-2">{action.new_status}</td>
                    <td className="border-b border-slate-100 px-3 py-2">{action.reason || '-'}</td>
                    <td className="border-b border-slate-100 px-3 py-2">{new Date(action.created_at).toLocaleString('en-IN')}</td>
                    <td className="border-b border-slate-100 px-3 py-2">
                      <button disabled={action.action_type === 'rollback'} onClick={() => rollbackAction(action.id)} className="text-xs font-medium text-blue-700 disabled:text-slate-400">
                        Rollback
                      </button>
                    </td>
                  </tr>
                ))}
                {!actions.isLoading && (actions.data || []).length === 0 && (
                  <tr><td colSpan={6} className="px-3 py-5 text-center text-sm text-slate-500">No manual actions yet.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <DataGrid rows={rows} columns={columns} />
    </div>
  );
}
