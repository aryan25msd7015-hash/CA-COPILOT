'use client';

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import PageHeader from '@/components/shared/PageHeader';
import { api } from '@/lib/api';

const SAMPLE_REQUEST = {
  txn: {
    account_id: 'A1',
    amount: 850000,
  },
  features: {
    new_beneficiary: 0.9,
    weekend: 0.25,
    device_change: 0.4,
    concentration: 0.6,
  },
  history: [
    { outflow_risk: 0.15, inflow_risk: 0.1, concentration_risk: 0.2 },
    { outflow_risk: 0.32, inflow_risk: 0.2, concentration_risk: 0.35 },
    { outflow_risk: 0.55, inflow_risk: 0.4, concentration_risk: 0.65 },
  ],
  graph_edges: [
    ['A1', 'A2', 1000],
    ['A2', 'A3', 2000],
    ['A3', 'A1', 1500],
  ],
};

interface Layer3Status {
  plugin: string;
  status: string;
  world_model_sequence_length: number;
  graph_nodes: number;
  graph_edges: number;
}

interface Layer3Result {
  current_risk: number;
  predicted_7d_risk: number;
  causal_explanation: string;
  top_causes: Array<{ feature: string; score: number; share: number }>;
  ring_summary: {
    account_id: string;
    rings_detected: number;
    ring_members: string[][];
    largest_ring_size: number;
  };
  visualization: {
    data: unknown[];
    layout?: Record<string, unknown>;
  };
}

export default function CausalAuditPage() {
  const [payloadText, setPayloadText] = useState(JSON.stringify(SAMPLE_REQUEST, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const status = useQuery<Layer3Status>({
    queryKey: ['layer3-causal-status'],
    queryFn: () => api.get('/layer3-causal/status').then(r => r.data),
  });

  const mutation = useMutation<Layer3Result, Error, Record<string, unknown>>({
    mutationFn: payload => api.post('/layer3-causal/analyze', payload).then(r => r.data),
  });

  const runAnalysis = () => {
    try {
      const parsed = JSON.parse(payloadText) as Record<string, unknown>;
      setJsonError(null);
      mutation.mutate(parsed);
    } catch {
      setJsonError('Invalid JSON payload.');
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Causal Audit Engine (Layer 3)"
        subtitle="Root-cause ranking, 7-day risk forecasting, and account-ring detection for suspicious money flow."
      />

      <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
        <div className="space-y-3 rounded-xl border bg-white p-4">
          <p className="text-sm font-medium">Causal analysis request</p>
          <textarea
            value={payloadText}
            onChange={event => setPayloadText(event.target.value)}
            rows={20}
            className="w-full rounded-lg border p-3 font-mono text-xs"
          />
          {jsonError && <p className="text-xs text-red-700">{jsonError}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPayloadText(JSON.stringify(SAMPLE_REQUEST, null, 2))}
              className="rounded-lg border px-3 py-2 text-xs"
            >
              Reset sample
            </button>
            <button
              type="button"
              onClick={runAnalysis}
              disabled={mutation.isPending}
              className="rounded-lg bg-cyan-700 px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
            >
              {mutation.isPending ? 'Running...' : 'Run Causal Audit'}
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
                <li><strong>Sequence length:</strong> {status.data.world_model_sequence_length}</li>
                <li><strong>Graph nodes:</strong> {status.data.graph_nodes}</li>
                <li><strong>Graph edges:</strong> {status.data.graph_edges}</li>
              </ul>
            )}
          </div>

          <p className="text-sm font-medium">Analysis result</p>
          {mutation.isError && (
            <p className="rounded-lg bg-red-50 p-3 text-xs text-red-700">
              {mutation.error.message || 'Causal analysis failed'}
            </p>
          )}
          {mutation.data && (
            <div className="space-y-3 text-xs">
              <div className="rounded-lg bg-gray-50 p-3">
                <p><strong>Current risk:</strong> {(mutation.data.current_risk * 100).toFixed(1)}%</p>
                <p><strong>Predicted 7D risk:</strong> {(mutation.data.predicted_7d_risk * 100).toFixed(1)}%</p>
                <p><strong>Explanation:</strong> {mutation.data.causal_explanation}</p>
              </div>
              <div className="rounded-lg border p-3">
                <p className="font-medium">Top causes</p>
                <ul className="mt-2 space-y-1">
                  {mutation.data.top_causes.map(item => (
                    <li key={item.feature}>
                      {item.feature}: score {item.score.toFixed(2)} · share {(item.share * 100).toFixed(1)}%
                    </li>
                  ))}
                </ul>
              </div>
              <div className="rounded-lg border p-3">
                <p className="font-medium">Ring summary</p>
                <p className="mt-1"><strong>Account:</strong> {mutation.data.ring_summary.account_id}</p>
                <p><strong>Rings:</strong> {mutation.data.ring_summary.rings_detected}</p>
                <p><strong>Largest ring:</strong> {mutation.data.ring_summary.largest_ring_size}</p>
              </div>
              <div className="max-h-[280px] overflow-auto rounded-lg bg-gray-900 p-3">
                <pre className="text-[11px] leading-5 text-gray-100">
                  {JSON.stringify(mutation.data.visualization, null, 2)}
                </pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
