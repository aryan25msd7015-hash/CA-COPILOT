'use client';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import FileUploadZone from '@/components/shared/FileUploadZone';
import PageHeader from '@/components/shared/PageHeader';
import TaskStatusPoller from '@/components/shared/TaskStatusPoller';
import StatusBadge from '@/components/shared/StatusBadge';

interface AuditResult {
  ratios?: Record<string, number>;
  observations?: string;
  provider?: string;
  export_mode?: string;
  generated_at?: string;
  period?: string;
}
export default function AuditPage() {
  const [clientId, setClientId] = useState('');
  const [documentId, setDocumentId] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<AuditResult | null>(null);
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  async function generate() {
    const response = await api.post('/audit-papers/generate', { document_id: documentId, period: 'Current financial year' });
    setTaskId(response.data.task_id);
  }
  async function download() {
    const response = await api.get(`/audit-papers/export/${documentId}`, { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const link = document.createElement('a');
    link.href = url;
    link.download = `audit-paper-${documentId}.docx`;
    link.click();
    URL.revokeObjectURL(url);
  }
  return <div className="space-y-5"><PageHeader title="AI Audit Working Papers" subtitle="Analyze a trial balance and generate ICAI-style observations." />
    <div className="grid gap-4 rounded-xl border bg-white p-4 md:grid-cols-2"><div className="space-y-3"><ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} /><FileUploadZone clientId={clientId} docType="trial_balance" onUploaded={setDocumentId} /></div><div className="space-y-3"><button disabled={!documentId} onClick={generate} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">Generate working paper</button><TaskStatusPoller taskId={taskId} onSuccess={data => setResult(data as AuditResult)} /></div></div>
    {result && <div className="space-y-5 rounded-xl border bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h2 className="font-medium">Key ratios</h2>
          <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
            <StatusBadge value="ready" />
            <span>Provider: {result.provider || 'unknown'}</span>
            <span>Export: {result.export_mode || 'unknown'}</span>
            {result.generated_at && <span>Generated: {new Date(result.generated_at).toLocaleString('en-IN')}</span>}
          </div>
        </div>
        <button onClick={download} className="rounded border px-3 py-2 text-sm text-blue-700">Download DOCX</button>
      </div>
      <div className="grid gap-3 md:grid-cols-4">{Object.entries(result.ratios || {}).map(([key, value]) => <div key={key} className="rounded-lg bg-gray-50 p-3"><p className="text-xs text-gray-500">{key.replaceAll('_', ' ')}</p><p className="mt-1 font-semibold">{value}</p></div>)}</div>
      <pre className="whitespace-pre-wrap rounded-lg bg-gray-50 p-4 text-sm leading-6 text-gray-700">{result.observations}</pre>
    </div>}
  </div>;
}
