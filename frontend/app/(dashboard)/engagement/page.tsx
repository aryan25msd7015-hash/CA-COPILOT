'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 160 },
  { field: 'engagement_type', headerName: 'Type', minWidth: 140 },
  { field: 'risk_category', headerName: 'Risk', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'kyc_status', headerName: 'KYC', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'letter_status', headerName: 'Letter', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  { field: 'udin', headerName: 'UDIN', minWidth: 120 },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
];

export default function EngagementPage() {
  return (
    <GapModulePage
      title="Engagement & KYC / AML"
      subtitle="UDIN-linked engagement letters, risk categorization, and ICAI KYC onboarding."
      endpoint="/practice-gaps/engagement"
      queryKey="engagement"
      columns={columns}
      defaults={{ engagement_type: 'statutory_audit', risk_category: 'medium', kyc_status: 'pending', letter_status: 'draft' }}
      createFields={[
        { key: 'engagement_type', label: 'Engagement type', type: 'select', options: ['statutory_audit', 'tax_audit', 'gst', 'retainer', 'advisory'] },
        { key: 'risk_category', label: 'Risk', type: 'select', options: ['low', 'medium', 'high'] },
        { key: 'kyc_status', label: 'KYC', type: 'select', options: ['pending', 'in_progress', 'complete'] },
        { key: 'udin', label: 'UDIN (optional)' },
        { key: 'letter_body', label: 'Engagement letter draft', type: 'textarea', required: true },
      ]}
      rowActions={(row, { patch, canApprove }) => (
        canApprove && row.status !== 'active' ? (
          <button className="rounded border px-2 py-1 text-xs" onClick={() => patch(String(row.id), { approve: true })}>
            Approve
          </button>
        ) : null
      )}
    />
  );
}
