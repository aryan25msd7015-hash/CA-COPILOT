'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 160 },
  { field: 'period', headerName: 'Period' },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'published_at', headerName: 'Published' },
  { field: 'narrative', headerName: 'Narrative', minWidth: 240 },
];

export default function MisPage() {
  return (
    <GapModulePage
      title="Virtual CFO / Recurring MIS"
      subtitle="Monthly MIS dashboards for retainer clients — upsell on top of compliance work."
      endpoint="/practice-gaps/mis"
      queryKey="mis"
      columns={columns}
      defaults={{ status: 'draft' }}
      createFields={[
        { key: 'period', label: 'Period (e.g. 2026-07)', required: true },
        { key: 'narrative', label: 'Narrative / commentary', type: 'textarea' },
      ]}
      rowActions={(row, { patch }) => (
        row.status !== 'published' ? (
          <button className="rounded border px-2 py-1 text-xs" onClick={() => patch(String(row.id), { publish: true })}>
            Publish
          </button>
        ) : null
      )}
    />
  );
}
