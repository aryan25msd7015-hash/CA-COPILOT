'use client';

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { api } from '@/lib/api';
import { downloadFromApi } from '@/lib/download';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface Vendor { id: string; vendor_name: string; vendor_gstin?: string; udyam_reg_no?: string; udyam_category: string; verified_at?: string; is_verified: boolean; has_udyam: boolean; }
interface Violation { id: string; vendor_name: string; vendor_gstin?: string; udyam_category: string; invoice_date: string; invoice_amount: number; due_date: string; days_overdue: number; disallowance_amount: number; interest_amount: number; fy: string; status: string; risk_bucket: string; }
interface MsmeOverview { vendor_count: number; verified_vendors: number; vendors_without_gstin: number; category_counts: Record<string, number>; open_violations: number; cleared_violations: number; affected_vendor_count: number; total_disallowance: number; total_interest: number; max_days_overdue: number; }
interface Clause22 { total_disallowance: number; total_interest: number; vendor_count: number; violation_count: number; max_days_overdue: number; category_breakdown: Record<string, { count: number; disallowance: number; interest: number }>; top_rows: { vendor_name: string; days_overdue: number; disallowance_amount: number; interest_amount: number }[]; }

export default function MsmePage() {
  const [clientId, setClientId] = useState('');
  const [fy, setFy] = useState(`${new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1}-${String((new Date().getMonth() >= 3 ? new Date().getFullYear() : new Date().getFullYear() - 1) + 1).slice(-2)}`);
  const [vendorCategory, setVendorCategory] = useState('');
  const [violationStatus, setViolationStatus] = useState('open');
  const [vendor, setVendor] = useState({ vendor_name: '', vendor_gstin: '', udyam_reg_no: '', udyam_category: 'micro', certificate_text: '' });
  const [message, setMessage] = useState('');
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const vendors = useQuery<Vendor[]>({ queryKey: ['msme-vendors', clientId, vendorCategory], queryFn: () => api.get(`/msme/vendors?client_id=${clientId}&udyam_category=${vendorCategory}`).then(r => r.data), enabled: !!clientId });
  const violations = useQuery<Violation[]>({ queryKey: ['msme-violations', clientId, fy, violationStatus], queryFn: () => api.get(`/msme/violations?client_id=${clientId}&fy=${fy}&status=${violationStatus}`).then(r => r.data), enabled: !!clientId });
  const overview = useQuery<MsmeOverview>({ queryKey: ['msme-overview', clientId, fy], queryFn: () => api.get(`/msme/overview?client_id=${clientId}&fy=${fy}`).then(r => r.data), enabled: !!clientId });
  const clause = useQuery<Clause22>({ queryKey: ['clause-22', clientId, fy], queryFn: () => api.get(`/msme/clause-22/${clientId}/${fy}`).then(r => r.data), enabled: !!clientId });
  async function createVendor() {
    await api.post('/msme/vendors', { client_id: clientId, ...vendor });
    setVendor({ vendor_name: '', vendor_gstin: '', udyam_reg_no: '', udyam_category: 'micro', certificate_text: '' });
    await vendors.refetch();
    setMessage('MSME vendor verified and saved.');
  }
  async function scan() {
    const response = await api.post('/msme/scan', { client_id: clientId, payment_dates: {} });
    await Promise.all([violations.refetch(), clause.refetch(), overview.refetch()]);
    setMessage(`${response.data.vendors_scanned} vendors and ${response.data.invoices_scanned} invoices scanned; ${response.data.new_violations} new, ${response.data.updated_violations} updated, ${response.data.cleared_violations} cleared. ${response.data.vendors_skipped} vendors skipped without GSTIN.`);
  }
  const vendorColumns = useMemo<ColDef<Vendor>[]>(() => [
    { field: 'vendor_name', headerName: 'Vendor', minWidth: 190 }, { field: 'vendor_gstin', headerName: 'GSTIN', minWidth: 160 },
    { field: 'udyam_reg_no', headerName: 'Udyam No.', minWidth: 180 }, { field: 'udyam_category', headerName: 'Category', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
    { field: 'is_verified', headerName: 'Verified', cellRenderer: (p: { value?: boolean }) => <StatusBadge value={p.value ? 'verified' : 'pending'} /> },
  ], []);
  const violationColumns = useMemo<ColDef<Violation>[]>(() => [
    { field: 'vendor_name', headerName: 'Vendor', minWidth: 180 }, { field: 'vendor_gstin', headerName: 'GSTIN', minWidth: 160 }, { field: 'invoice_date', headerName: 'Invoice date' }, { field: 'due_date', headerName: '45-day due date' },
    { field: 'days_overdue', headerName: 'Days overdue' }, { field: 'disallowance_amount', headerName: 'Disallowance', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'interest_amount', headerName: 'MSMED interest', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
    { field: 'risk_bucket', headerName: 'Risk', cellRenderer: (p: { value?: string }) => <StatusBadge value={`risk_${p.value === 'severe' ? 'high' : p.value || 'low'}`} /> },
    { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  ], []);
  const metrics = [
    ['Vendors', overview.data?.vendor_count || 0],
    ['Verified', overview.data?.verified_vendors || 0],
    ['Open violations', overview.data?.open_violations || 0],
    ['Affected vendors', overview.data?.affected_vendor_count || 0],
    ['Max overdue', `${overview.data?.max_days_overdue || 0} days`],
    ['Disallowance', `INR ${Number(overview.data?.total_disallowance || 0).toLocaleString('en-IN')}`],
    ['MSMED interest', `INR ${Number(overview.data?.total_interest || 0).toLocaleString('en-IN')}`],
    ['Missing GSTIN', overview.data?.vendors_without_gstin || 0],
  ];
  return <div className="space-y-5">
    <PageHeader title="MSME Payment Audit" subtitle="Section 43B(h) vendor verification, 45-day monitoring, and Clause 22 reporting." />
    <div className="flex flex-wrap gap-3 rounded-xl border bg-white p-4"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><input value={fy} onChange={e => setFy(e.target.value)} className="rounded-lg border px-3 py-2 text-sm" placeholder="FY 2026-27" /><select value={violationStatus} onChange={e => setViolationStatus(e.target.value)} className="rounded-lg border px-3 py-2 text-sm"><option value="">All violations</option><option value="open">Open</option><option value="cleared">Cleared</option></select><select value={vendorCategory} onChange={e => setVendorCategory(e.target.value)} className="rounded-lg border px-3 py-2 text-sm"><option value="">All categories</option><option value="micro">Micro</option><option value="small">Small</option><option value="medium">Medium</option></select><button disabled={!clientId} onClick={scan} className="rounded-lg bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-50">Scan AP ledger</button><button disabled={!clientId} onClick={() => downloadFromApi(`/msme/export/${clientId}/${fy}`, `msme-clause-22-${fy}.xlsx`)} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">Export Clause 22</button></div>
    {clientId && <div className="grid gap-3 rounded-xl border bg-white p-4 md:grid-cols-4"><input value={vendor.vendor_name} onChange={e => setVendor({ ...vendor, vendor_name: e.target.value })} placeholder="Vendor name" className="rounded border px-3 py-2 text-sm" /><input value={vendor.vendor_gstin} onChange={e => setVendor({ ...vendor, vendor_gstin: e.target.value })} placeholder="Vendor GSTIN" className="rounded border px-3 py-2 text-sm" /><input value={vendor.udyam_reg_no} onChange={e => setVendor({ ...vendor, udyam_reg_no: e.target.value })} placeholder="Udyam number" className="rounded border px-3 py-2 text-sm" /><select value={vendor.udyam_category} onChange={e => setVendor({ ...vendor, udyam_category: e.target.value })} className="rounded border px-3 py-2 text-sm"><option>micro</option><option>small</option><option>medium</option></select><textarea value={vendor.certificate_text} onChange={e => setVendor({ ...vendor, certificate_text: e.target.value })} placeholder="Optional OCR text from Udyam certificate" className="md:col-span-3 rounded border px-3 py-2 text-sm" /><button onClick={createVendor} className="rounded bg-gray-900 px-3 py-2 text-sm text-white">Verify & add vendor</button></div>}
    {message && <p className="text-sm text-green-700">{message}</p>}
    <div className="grid gap-3 sm:grid-cols-4">{metrics.map(([label, value]) => <div key={label} className="rounded-xl border bg-white p-4"><p className="text-xs text-gray-500">{label}</p><p className="mt-1 text-lg font-semibold">{value}</p></div>)}</div>
    {clause.data && <div className="grid gap-3 rounded-xl border bg-white p-4 md:grid-cols-3">
      {Object.entries(clause.data.category_breakdown || {}).map(([category, row]) => <div key={category} className="rounded-lg border p-3"><div className="flex items-center justify-between"><StatusBadge value={category} /><span className="text-xs text-gray-500">{row.count} rows</span></div><p className="mt-2 text-sm font-semibold">INR {Number(row.disallowance).toLocaleString('en-IN')}</p><p className="text-xs text-gray-500">Interest INR {Number(row.interest).toLocaleString('en-IN')}</p></div>)}
      {!Object.keys(clause.data.category_breakdown || {}).length && <p className="text-sm text-gray-500">No open Clause 22 exceptions for this financial year.</p>}
    </div>}
    <div><h2 className="mb-2 text-sm font-semibold">MSME vendor registry</h2><DataGrid rows={vendors.data || []} columns={vendorColumns} /></div>
    <div><h2 className="mb-2 text-sm font-semibold">Section 43B(h) violations</h2><DataGrid rows={violations.data || []} columns={violationColumns} /></div>
  </div>;
}
