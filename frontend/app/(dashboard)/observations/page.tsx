'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 150 },
  { field: 'area', headerName: 'Area' },
  { field: 'query_text', headerName: 'Query', minWidth: 240 },
  { field: 'raised_to', headerName: 'Raised to' },
  { field: 'due_date', headerName: 'Due' },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'response_text', headerName: 'Response', minWidth: 180 },
];

export default function ObservationsPage() {
  return (
    <GapModulePage
      title="Query & Observation Ledger"
      subtitle="Structured fieldwork queries, client responses, and resolution status — replace WhatsApp chaos."
      endpoint="/practice-gaps/observations"
      queryKey="observations"
      columns={columns}
      createFields={[
        { key: 'area', label: 'Area (e.g. Inventory)', required: true },
        { key: 'engagement_ref', label: 'Engagement ref' },
        { key: 'raised_to', label: 'Raised to' },
        { key: 'due_date', label: 'Due date', type: 'date' },
        { key: 'query_text', label: 'Query / observation', type: 'textarea', required: true },
      ]}
      rowActions={(row, { patch, canApprove }) => (
        canApprove && row.status !== 'closed' ? (
          <button className="rounded border px-2 py-1 text-xs" onClick={() => patch(String(row.id), { close: true })}>
            Close
          </button>
        ) : null
      )}
    />
  );
}
