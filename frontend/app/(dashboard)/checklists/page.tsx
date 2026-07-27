'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 150 },
  { field: 'framework', headerName: 'Framework' },
  { field: 'entity_type', headerName: 'Entity' },
  { field: 'fy', headerName: 'FY' },
  { field: 'completion_pct', headerName: '% done', valueFormatter: p => `${Number(p.value || 0)}%` },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
];

export default function ChecklistsPage() {
  return (
    <GapModulePage
      title="Statutory Audit Checklist Engine"
      subtitle="Companies Act / CARO checklists that auto-populate by entity type. Sign-off gated to CA (Manager)+."
      endpoint="/practice-gaps/checklists"
      queryKey="checklists"
      columns={columns}
      defaults={{ framework: 'CARO', entity_type: 'pvt_ltd' }}
      createFields={[
        { key: 'framework', label: 'Framework', type: 'select', options: ['CARO', 'CompaniesAct', 'IncomeTax'] },
        { key: 'entity_type', label: 'Entity type', type: 'select', options: ['pvt_ltd', 'public', 'llp', 'opc'] },
        { key: 'fy', label: 'FY', required: true },
      ]}
      primaryActionLabel="Generate checklist"
      rowActions={(row, { patch, canApprove }) => (
        canApprove && row.status !== 'signed_off' ? (
          <button className="rounded border px-2 py-1 text-xs" onClick={() => patch(String(row.id), { signoff: true })}>
            Sign off
          </button>
        ) : null
      )}
    />
  );
}
