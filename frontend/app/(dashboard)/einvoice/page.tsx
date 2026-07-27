'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 150 },
  { field: 'invoice_no', headerName: 'Invoice' },
  { field: 'irn', headerName: 'IRN', minWidth: 180 },
  { field: 'turnover_threshold_hit', headerName: 'Threshold', cellRenderer: (p: { value?: boolean }) => <StatusBadge value={p.value ? 'applicable' : 'below'} /> },
  { field: 'status', headerName: 'Status', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
];

export default function EinvoicePage() {
  return (
    <GapModulePage
      title="E-Invoice / IRN Validation"
      subtitle="Validate IRN generation compliance for clients above the e-invoicing turnover threshold."
      endpoint="/practice-gaps/einvoice"
      queryKey="einvoice"
      columns={columns}
      defaults={{ status: 'pending' }}
      createFields={[
        { key: 'invoice_no', label: 'Invoice number', required: true },
        { key: 'irn', label: 'IRN' },
      ]}
      primaryActionLabel="Validate"
    />
  );
}
