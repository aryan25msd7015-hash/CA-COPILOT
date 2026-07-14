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

interface Facility { id: string; bank_name: string; facility_type: string; sanctioned_limit: number; margin_rules: Record<string, unknown>; latest_period?: string; latest_drawing_power: number; utilization_pct?: number; }
interface Statement { id: string; period: string; bank_name: string; facility_type: string; sanctioned_limit: number; gross_stock: number; eligible_stock: number; gross_debtors: number; eligible_debtors: number; creditors: number; drawing_power: number; utilization_pct: number; stock_dp: number; debtor_dp: number; ineligible_stock: number; ineligible_debtors: number; at_risk_debtors: number; }
interface Overview { facility_count: number; statement_count: number; inventory_items: number; debtor_items: number; sanctioned_limit: number; drawing_power: number; available_headroom: number; average_utilization_pct: number; ineligible_stock: number; ineligible_debtors: number; at_risk_debtors: number; }
const inventoryExample = JSON.stringify([{ sku: 'RM-100', description: 'Raw material', stock_value: 500000, last_movement_date: '2026-06-01' }], null, 2);
const debtorExample = JSON.stringify([{ debtor_name: 'Alpha Customer', invoice_date: '2026-05-01', outstanding: 300000, payment_history_score: 88 }], null, 2);

export default function DrawingPowerPage() {
  const [clientId, setClientId] = useState('');
  const [facilityId, setFacilityId] = useState('');
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [creditors, setCreditors] = useState(0);
  const [facility, setFacility] = useState({ bank_name: '', facility_type: 'CC', sanctioned_limit: 1000000 });
  const [rules, setRules] = useState({ stock_margin: .25, debtor_margin: .25, stock_age_cutoff_days: 180, debtor_age_cutoff_days: 90, creditor_deduction: true });
  const [inventory, setInventory] = useState(inventoryExample);
  const [debtors, setDebtors] = useState(debtorExample);
  const [message, setMessage] = useState('');
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const facilities = useQuery<Facility[]>({ queryKey: ['dp-facilities', clientId], queryFn: () => api.get(`/drawing-power/facilities?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  const statements = useQuery<Statement[]>({ queryKey: ['dp-statements', clientId], queryFn: () => api.get(`/drawing-power/statements?client_id=${clientId}`).then(r => r.data), enabled: !!clientId });
  const overview = useQuery<Overview>({ queryKey: ['dp-overview', clientId, period], queryFn: () => api.get(`/drawing-power/overview?client_id=${clientId}&period=${period}`).then(r => r.data), enabled: !!clientId });
  async function addFacility() {
    const response = await api.post('/drawing-power/facilities', { client_id: clientId, ...facility, margin_rules: rules });
    await Promise.all([facilities.refetch(), overview.refetch()]); setFacilityId(response.data.id); setMessage('Bank facility saved.');
  }
  async function importAndCompute() {
    const ledger = await api.post('/drawing-power/ledger', { client_id: clientId, period, inventory: JSON.parse(inventory), debtors: JSON.parse(debtors) });
    const response = await api.post('/drawing-power/compute', { facility_id: facilityId, period, creditors });
    await Promise.all([statements.refetch(), facilities.refetch(), overview.refetch()]);
    setMessage(`Drawing power computed: INR ${Number(response.data.drawing_power).toLocaleString('en-IN')}. Imported ${ledger.data.inventory_count} stock rows and ${ledger.data.debtor_count} debtor rows; ${ledger.data.rejected_count} rejected.`);
  }
  const columns = useMemo<ColDef<Statement>[]>(() => [
    { field: 'period', headerName: 'Period' }, { field: 'bank_name', headerName: 'Bank', minWidth: 160 }, { field: 'facility_type', headerName: 'Type', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
    { field: 'gross_stock', headerName: 'Gross stock', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'eligible_stock', headerName: 'Eligible stock', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'gross_debtors', headerName: 'Gross debtors', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'eligible_debtors', headerName: 'Eligible debtors', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` }, { field: 'creditors', headerName: 'Creditors', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'drawing_power', headerName: 'Drawing power', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'utilization_pct', headerName: 'Utilization', valueFormatter: p => `${Number(p.value || 0).toFixed(1)}%` },
    { headerName: 'Exports', minWidth: 150, sortable: false, filter: false, cellRenderer: (p: ICellRendererParams<Statement>) => <div className="flex h-full items-center gap-3"><button onClick={() => p.data && downloadFromApi(`/drawing-power/export/${p.data.id}.pdf`, `drawing-power-${p.data.period}.pdf`)} className="text-xs text-blue-700">PDF</button><button onClick={() => p.data && downloadFromApi(`/drawing-power/export/${p.data.id}.xlsx`, `drawing-power-${p.data.period}.xlsx`)} className="text-xs text-green-700">Excel</button></div> },
  ], []);
  const selectedFacility = (facilities.data || []).find(row => row.id === facilityId);
  const metrics = [
    ['Facilities', overview.data?.facility_count || 0],
    ['Statements', overview.data?.statement_count || 0],
    ['Sanctioned limit', `INR ${Number(overview.data?.sanctioned_limit || 0).toLocaleString('en-IN')}`],
    ['Drawing power', `INR ${Number(overview.data?.drawing_power || 0).toLocaleString('en-IN')}`],
    ['Headroom', `INR ${Number(overview.data?.available_headroom || 0).toLocaleString('en-IN')}`],
    ['Utilization', `${Number(overview.data?.average_utilization_pct || 0).toFixed(1)}%`],
    ['Ineligible stock', `INR ${Number(overview.data?.ineligible_stock || 0).toLocaleString('en-IN')}`],
    ['At-risk debtors', overview.data?.at_risk_debtors || 0],
  ];
  return <div className="space-y-5">
    <PageHeader title="Drawing Power & Stock Statements" subtitle="Apply bank-specific margins, aging rules, and sanctioned-limit caps." />
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><ClientSelect clients={clients.data || []} value={clientId} onChange={value => { setClientId(value); setFacilityId(''); }} /><select value={facilityId} onChange={e => setFacilityId(e.target.value)} className="rounded-lg border px-3 py-2 text-sm"><option value="">Select facility</option>{(facilities.data || []).map(row => <option key={row.id} value={row.id}>{row.bank_name} | {row.facility_type} | INR {Number(row.sanctioned_limit).toLocaleString('en-IN')}</option>)}</select><input type="month" value={period} onChange={e => setPeriod(e.target.value)} className="rounded-lg border px-3 py-2 text-sm" /><input type="number" value={creditors} onChange={e => setCreditors(Number(e.target.value))} placeholder="Creditors" className="rounded-lg border px-3 py-2 text-sm" /><button disabled={!facilityId} onClick={importAndCompute} className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Import ledgers & compute</button></div>
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    {selectedFacility && <div className="rounded-xl border bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-3"><div><p className="text-sm font-semibold">{selectedFacility.bank_name} facility</p><p className="text-xs text-gray-500">Latest period {selectedFacility.latest_period || 'not computed'} | Latest DP INR {Number(selectedFacility.latest_drawing_power || 0).toLocaleString('en-IN')}</p></div><StatusBadge value={Number(selectedFacility.utilization_pct || 0) > 90 ? 'risk_high' : Number(selectedFacility.utilization_pct || 0) > 70 ? 'risk_medium' : 'risk_low'} /></div></div>}
    {clientId && <div className="grid gap-3 rounded-xl border bg-white p-4 md:grid-cols-4">
      <input value={facility.bank_name} onChange={e => setFacility({ ...facility, bank_name: e.target.value })} placeholder="Bank name" className="rounded border px-3 py-2 text-sm" />
      <select value={facility.facility_type} onChange={e => setFacility({ ...facility, facility_type: e.target.value })} className="rounded border px-3 py-2 text-sm"><option>CC</option><option>OD</option><option>WCDL</option><option>FBP</option><option>PCFC</option></select>
      <input type="number" value={facility.sanctioned_limit} onChange={e => setFacility({ ...facility, sanctioned_limit: Number(e.target.value) })} placeholder="Sanctioned limit" className="rounded border px-3 py-2 text-sm" />
      <input type="number" step="0.01" min="0" max="1" value={rules.stock_margin} onChange={e => setRules({ ...rules, stock_margin: Number(e.target.value) })} placeholder="Stock margin (0.25)" className="rounded border px-3 py-2 text-sm" />
      <input type="number" step="0.01" min="0" max="1" value={rules.debtor_margin} onChange={e => setRules({ ...rules, debtor_margin: Number(e.target.value) })} placeholder="Debtor margin (0.25)" className="rounded border px-3 py-2 text-sm" />
      <input type="number" value={rules.stock_age_cutoff_days} onChange={e => setRules({ ...rules, stock_age_cutoff_days: Number(e.target.value) })} placeholder="Stock age cutoff days" className="rounded border px-3 py-2 text-sm" />
      <input type="number" value={rules.debtor_age_cutoff_days} onChange={e => setRules({ ...rules, debtor_age_cutoff_days: Number(e.target.value) })} placeholder="Debtor age cutoff days" className="rounded border px-3 py-2 text-sm" />
      <label className="flex items-center gap-2 rounded border px-3 py-2 text-sm"><input type="checkbox" checked={rules.creditor_deduction} onChange={e => setRules({ ...rules, creditor_deduction: e.target.checked })} />Deduct creditors</label>
      <button onClick={addFacility} disabled={!facility.bank_name} className="rounded bg-gray-900 px-3 py-2 text-sm text-white disabled:opacity-50">Add bank-specific facility</button>
    </div>}
    <div className="grid gap-4 md:grid-cols-2"><label className="text-sm font-medium">Inventory ledger JSON<textarea value={inventory} onChange={e => setInventory(e.target.value)} rows={10} className="mt-1 w-full rounded-xl border p-3 font-mono text-xs" /></label><label className="text-sm font-medium">Debtor ledger JSON<textarea value={debtors} onChange={e => setDebtors(e.target.value)} rows={10} className="mt-1 w-full rounded-xl border p-3 font-mono text-xs" /></label></div>
    {message && <p className="text-sm text-green-700">{message}</p>}
    <DataGrid rows={statements.data || []} columns={columns} />
  </div>;
}
