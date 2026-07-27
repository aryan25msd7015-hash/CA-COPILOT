'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'cycle_label', headerName: 'Cycle', minWidth: 140 },
  { field: 'readiness_score', headerName: 'Readiness', valueFormatter: p => `${Number(p.value || 0)}%` },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'created_at', headerName: 'Created', minWidth: 160 },
];

export default function PeerReviewPage() {
  return (
    <GapModulePage
      title="Peer Review / QC"
      subtitle="ICAI peer-review readiness packs — partner-only governance module."
      endpoint="/practice-gaps/peer-review"
      queryKey="peer-review"
      columns={columns}
      requireClient={false}
      defaults={{ status: 'open', readiness_score: 0 }}
      createFields={[
        { key: 'cycle_label', label: 'Cycle label (e.g. PR-2026)', required: true },
        { key: 'readiness_score', label: 'Readiness %', type: 'number' },
      ]}
    />
  );
}
