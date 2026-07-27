'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 150 },
  { field: 'period', headerName: 'Period' },
  { field: 'source', headerName: 'Source' },
  { field: 'books_total', headerName: 'Books', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
  { field: 'portal_total', headerName: '26AS/AIS', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
  { field: 'variance', headerName: 'Variance', valueFormatter: p => `INR ${Number(p.value || 0).toLocaleString('en-IN')}` },
  { field: 'exception_count', headerName: 'Exceptions' },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
];

export default function TdsPage() {
  return (
    <GapModulePage
      title="TDS / TCS Reconciliation"
      subtitle="Match 26AS / AIS / TRACES against books — the highest-volume manual task in CA offices."
      endpoint="/practice-gaps/tds-recon"
      queryKey="tds-recon"
      columns={columns}
      defaults={{ source: '26AS', status: 'draft', books_total: 0, portal_total: 0 }}
      createFields={[
        { key: 'period', label: 'Period (FY / Qtr)', required: true },
        { key: 'source', label: 'Source', type: 'select', options: ['26AS', 'AIS', 'TRACES'] },
        { key: 'books_total', label: 'Books total', type: 'number' },
        { key: 'portal_total', label: 'Portal total', type: 'number' },
        { key: 'exception_count', label: 'Exception count', type: 'number' },
      ]}
      rowActions={(row, { patch, canApprove }) => (
        canApprove && row.status !== 'closed' ? (
          <button className="rounded border px-2 py-1 text-xs" onClick={() => patch(String(row.id), { mark_reviewed: true })}>
            Approve
          </button>
        ) : null
      )}
    />
  );
}
