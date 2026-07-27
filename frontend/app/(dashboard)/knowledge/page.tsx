'use client';

import type { ColDef } from 'ag-grid-community';
import GapModulePage from '@/components/shared/GapModulePage';
import StatusBadge from '@/components/shared/StatusBadge';

const columns: ColDef[] = [
  { field: 'topic', headerName: 'Topic' },
  { field: 'title', headerName: 'Title', minWidth: 200 },
  { field: 'published', headerName: 'Published', cellRenderer: (p: { value?: boolean }) => <StatusBadge value={p.value ? 'published' : 'draft'} /> },
  { field: 'updated_at', headerName: 'Updated', minWidth: 160 },
];

export default function KnowledgePage() {
  return (
    <GapModulePage
      title="SOP / Knowledge Base"
      subtitle="Internal wiki for firm procedures so interns stop pinging seniors for the same answer."
      endpoint="/practice-gaps/knowledge"
      queryKey="knowledge"
      columns={columns}
      requireClient={false}
      defaults={{ topic: 'gst', published: true }}
      createFields={[
        { key: 'topic', label: 'Topic', type: 'select', options: ['gst', 'income_tax', 'audit', 'secretarial', 'office'] },
        { key: 'title', label: 'Title', required: true },
        { key: 'body', label: 'SOP body', type: 'textarea', required: true },
      ]}
    />
  );
}
