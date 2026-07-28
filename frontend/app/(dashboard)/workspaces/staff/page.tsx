'use client';

import { useQuery } from '@tanstack/react-query';
import RoleShell from '@/components/layout/RoleShell';
import { api } from '@/lib/api';

export default function StaffWorkspacePage() {
  const deadlines = useQuery<Array<{ id?: string; filing_type?: string; filing_name?: string; status?: string }> | { items?: Array<{ id?: string; filing_type?: string; filing_name?: string; status?: string }> }>({
    queryKey: ['staff-deadlines'],
    queryFn: () => api.get('/deadlines', { params: { limit: 20 } }).then(r => r.data).catch(() => []),
  });
  const documents = useQuery<Array<{ id: string; doc_type?: string; status?: string }> | { items?: Array<{ id: string; doc_type?: string; status?: string }> }>({
    queryKey: ['staff-documents'],
    queryFn: () => api.get('/documents', { params: { limit: 20 } }).then(r => r.data).catch(() => []),
  });

  const deadlineRows = Array.isArray(deadlines.data) ? deadlines.data : deadlines.data?.items || [];
  const documentRows = Array.isArray(documents.data) ? documents.data : documents.data?.items || [];

  return (
    <RoleShell
      title="Intern / Staff Workbench"
      subtitle="Execution-only desk: drafts, uploads, reconciliations and fieldwork. No approvals or partner lock-downs."
      accent="staff"
      allowedFeatures={[
        'command_center',
        'work_daybook',
        'document_vault',
        'compliance_calendar',
        'gst_reconciliation',
        'guided_imports',
        'query_observation_ledger',
        'statutory_checklist',
        'ask_ca_copilot',
      ]}
    >
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-xl border border-stone-300 bg-white p-4">
          <h2 className="text-lg font-semibold text-stone-950">Today’s execution queue</h2>
          <p className="text-sm text-stone-600">Deadlines and filings waiting on draft work.</p>
          <ul className="mt-4 space-y-2 text-sm">
            {deadlineRows.slice(0, 8).map(row => (
              <li key={row.id || row.filing_type} className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-stone-800">
                {row.filing_name || row.filing_type || 'Filing'} · {row.status || 'pending'}
              </li>
            ))}
            {!deadlineRows.length && <li className="text-stone-600">No deadline feed available yet.</li>}
          </ul>
        </section>
        <section className="rounded-xl border border-stone-300 bg-white p-4">
          <h2 className="text-lg font-semibold text-stone-950">Document intake</h2>
          <p className="text-sm text-stone-600">Upload, OCR check, and prepare for manager review.</p>
          <ul className="mt-4 space-y-2 text-sm">
            {documentRows.slice(0, 8).map(row => (
              <li key={row.id} className="rounded-md border border-stone-200 bg-stone-50 px-3 py-2 text-stone-800">
                {row.doc_type || 'document'} · {row.status || 'pending'}
              </li>
            ))}
            {!documentRows.length && <li className="text-stone-600">No documents in queue.</li>}
          </ul>
        </section>
      </div>
    </RoleShell>
  );
}
