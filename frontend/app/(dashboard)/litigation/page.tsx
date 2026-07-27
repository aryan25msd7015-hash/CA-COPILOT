'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 150 },
  { field: 'forum', headerName: 'Forum' },
  { field: 'case_no', headerName: 'Case no.', minWidth: 140 },
  { field: 'ay_or_period', headerName: 'AY / Period' },
  { field: 'next_hearing_date', headerName: 'Next hearing' },
  { field: 'submission_due', headerName: 'Submission due' },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'matter_summary', headerName: 'Matter', minWidth: 220 },
];

export default function LitigationPage() {
  return (
    <GapModulePage
      title="Litigation & Hearing Tracker"
      subtitle="CIT(A) / ITAT / GST appeal status, hearing dates, and submission deadlines."
      endpoint="/practice-gaps/litigation"
      queryKey="litigation"
      columns={columns}
      defaults={{ forum: 'CIT(A)', status: 'open' }}
      createFields={[
        { key: 'forum', label: 'Forum', type: 'select', options: ['CIT(A)', 'ITAT', 'GST', 'HC', 'SC'] },
        { key: 'case_no', label: 'Case number', required: true },
        { key: 'ay_or_period', label: 'AY / Period' },
        { key: 'next_hearing_date', label: 'Next hearing', type: 'date' },
        { key: 'submission_due', label: 'Submission due', type: 'date' },
        { key: 'counsel_name', label: 'Counsel' },
        { key: 'matter_summary', label: 'Matter summary', type: 'textarea', required: true },
      ]}
      rowActions={(row, { patch, canApprove }) => (
        canApprove && row.status !== 'closed' ? (
          <button className="rounded border px-2 py-1 text-xs" onClick={() => patch(String(row.id), { status: 'closed' })}>
            Close
          </button>
        ) : null
      )}
    />
  );
}
