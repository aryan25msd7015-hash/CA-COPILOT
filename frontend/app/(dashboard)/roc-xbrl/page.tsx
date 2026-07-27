'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 150 },
  { field: 'form_name', headerName: 'Form' },
  { field: 'fy', headerName: 'FY' },
  { field: 'due_date', headerName: 'Due' },
  { field: 'validation_status', headerName: 'XBRL validation', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'cost_audit_applicable', headerName: 'Cost audit', cellRenderer: (p: { value?: boolean }) => <StatusBadge value={p.value ? 'yes' : 'no'} /> },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
];

export default function RocXbrlPage() {
  return (
    <GapModulePage
      title="ROC / XBRL Filing Tracker"
      subtitle="Track AOC-4 / MGT-7 / XBRL validation status, due dates, and cost-audit applicability."
      endpoint="/practice-gaps/roc-xbrl"
      queryKey="roc-xbrl"
      columns={columns}
      defaults={{ form_name: 'AOC-4', validation_status: 'pending', status: 'open' }}
      createFields={[
        { key: 'form_name', label: 'Form', type: 'select', options: ['AOC-4', 'MGT-7', 'XBRL', 'AOC-4-XBRL'] },
        { key: 'fy', label: 'FY', required: true },
        { key: 'due_date', label: 'Due date', type: 'date' },
        { key: 'notes', label: 'Notes', type: 'textarea' },
      ]}
    />
  );
}
