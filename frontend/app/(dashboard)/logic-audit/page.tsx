'use client';

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import PageHeader from '@/components/shared/PageHeader';
import { api } from '@/lib/api';

const SAMPLE_TXN = {
  txn_id: 'txn-demo-001',
  account_id: 'ACC-1001',
  amount: 1250000,
  timestamp: '2026-07-25T10:30:00Z',
  pan: 'ABCDE1234F',
  gstin: '27ABCDE1234F1Z5',
  device_id: 'DEV-01',
  beneficiary_account: 'ACC-2002',
  is_new_beneficiary: true,
  days_since_beneficiary_added: 1,
  txn_count_24h: 4,
  total_amount_24h: 1400000,
  txn_count_1h: 6,
  total_amount_1h: 750000,
  days_since_last_txn: 120,
  is_round_amount: true,
  is_international: true,
  pan_gstin_mismatch: true,
  device_change_24h: 3,
};

interface AuditResult {
  is_flagged: boolean;
  rules_hit: string[];
  proof: Record<string, string>;
}

interface PluginStatus {
  plugin: string;
  status: string;
  rules_loaded: number;
  graph_nodes: number;
  graph_edges: number;
}

export default function LogicAuditPage() {
  const [payloadText, setPayloadText] = useState(JSON.stringify(SAMPLE_TXN, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const status = useQuery<PluginStatus>({
    queryKey: ['layer1-audit-status'],
    queryFn: () => api.get('/layer1-audit/status').then(r => r.data),
  });

  const mutation = useMutation<AuditResult, Error, Record<string, unknown>>({
    mutationFn: txn => api.post('/layer1-audit/audit-txn', { txn }).then(r => r.data),
  });

  const runAudit = () => {
    try {
      const parsedTxn = JSON.parse(payloadText) as Record<string, unknown>;
      setJsonError(null);
      mutation.mutate(parsedTxn);
    } catch {
      setJsonError('Invalid JSON payload.');
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Logic Audit Engine (Layer 1)"
        subtitle="RBI/PMLA rule checks with formal Z3 proof strings and account-PAN-GSTIN-device link intelligence."
      />

      <div className="grid gap-4 lg:grid-cols-[1.25fr_1fr]">
        <div className="space-y-3 rounded-xl border bg-white p-4">
          <p className="text-sm font-medium">Transaction payload (JSON)</p>
          <textarea
            value={payloadText}
            onChange={event => setPayloadText(event.target.value)}
            rows={18}
            className="w-full rounded-lg border p-3 font-mono text-xs"
          />
          {jsonError && <p className="text-xs text-red-700">{jsonError}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPayloadText(JSON.stringify(SAMPLE_TXN, null, 2))}
              className="rounded-lg border px-3 py-2 text-xs"
            >
              Reset sample
            </button>
            <button
              type="button"
              onClick={runAudit}
              disabled={mutation.isPending}
              className="rounded-lg bg-cyan-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
            >
              {mutation.isPending ? 'Running...' : 'Run Logic Audit'}
            </button>
          </div>
        </div>

        <div className="space-y-3 rounded-xl border bg-white p-4">
          <p className="text-sm font-medium">Plugin status</p>
          <div className="rounded-lg bg-gray-50 p-3 text-xs">
            {status.isLoading && 'Loading status...'}
            {status.data && (
              <ul className="space-y-1">
                <li><strong>Plugin:</strong> {status.data.plugin}</li>
                <li><strong>Status:</strong> {status.data.status}</li>
                <li><strong>Rules loaded:</strong> {status.data.rules_loaded}</li>
                <li><strong>Graph nodes:</strong> {status.data.graph_nodes}</li>
                <li><strong>Graph edges:</strong> {status.data.graph_edges}</li>
              </ul>
            )}
          </div>

          <p className="text-sm font-medium">Audit result</p>
          {mutation.isError && (
            <p className="rounded-lg bg-red-50 p-3 text-xs text-red-700">
              {mutation.error.message || 'Audit execution failed'}
            </p>
          )}
          {mutation.data && (
            <div className="space-y-3">
              <div className="rounded-lg bg-gray-50 p-3 text-xs">
                <p><strong>Flagged:</strong> {mutation.data.is_flagged ? 'Yes' : 'No'}</p>
                <p><strong>Rules hit:</strong> {mutation.data.rules_hit.join(', ') || '-'}</p>
              </div>
              <div className="max-h-[360px] overflow-auto rounded-lg bg-gray-900 p-3">
                <pre className="text-[11px] leading-5 text-gray-100">
                  {JSON.stringify(mutation.data.proof, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
