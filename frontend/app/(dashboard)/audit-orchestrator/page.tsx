'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import PageHeader from '@/components/shared/PageHeader';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { api } from '@/lib/api';

const SAMPLE_TXN = {
  txn_id: 'txn-orch-001',
  account_id: 'ACC-7789',
  amount: 1250000,
  timestamp: '2026-07-28T09:30:00Z',
  gstin: '27ABCDE1234F1Z5',
  pan: 'ABCDE1234F',
  device_id: 'DEV-77',
  beneficiary_account: 'ACC-9100',
  is_new_beneficiary: true,
  txn_count_24h: 6,
  total_amount_24h: 2100000,
  txn_count_1h: 5,
  total_amount_1h: 900000,
  days_since_last_txn: 102,
  is_round_amount: true,
  is_international: true,
  pan_gstin_mismatch: false,
  device_change_24h: 2,
  features: {
    new_beneficiary: 0.88,
    weekend: 0.3,
    device_change: 0.6,
    concentration: 0.72,
  },
  history: [
    { outflow_risk: 0.2, inflow_risk: 0.1, concentration_risk: 0.25 },
    { outflow_risk: 0.45, inflow_risk: 0.2, concentration_risk: 0.5 },
    { outflow_risk: 0.61, inflow_risk: 0.35, concentration_risk: 0.7 },
  ],
  graph_edges: [
    ['ACC-7789', 'ACC-901', 100000],
    ['ACC-901', 'ACC-455', 90000],
    ['ACC-455', 'ACC-7789', 95000],
  ],
};

interface AuditResponse {
  investigation_id: string;
  final_risk: 'low' | 'medium' | 'high' | 'critical';
  remark: string;
  risk_score: number;
  proof: Record<string, string>;
  evidence_pack: Record<string, unknown>;
}

export default function AuditOrchestratorPage() {
  const [payloadText, setPayloadText] = useState(JSON.stringify(SAMPLE_TXN, null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [feedbackNote, setFeedbackNote] = useState<string>('');

  const auditMutation = useMutation<AuditResponse, Error, Record<string, unknown>>({
    mutationFn: txn => api.post('/audit_txn', txn).then(r => r.data),
  });

  const feedbackMutation = useMutation<
    { approved: boolean; rl_update: { reward: number; learning_steps: number } },
    Error,
    { investigation_id: string; approved: boolean }
  >({
    mutationFn: body => api.post('/audit_txn/feedback', body).then(r => r.data),
  });

  const runPipeline = () => {
    try {
      const parsed = JSON.parse(payloadText) as Record<string, unknown>;
      setJsonError(null);
      setFeedbackNote('');
      auditMutation.mutate(parsed);
    } catch {
      setJsonError('Invalid JSON payload.');
    }
  };

  const sendFeedback = (approved: boolean) => {
    const investigationId = auditMutation.data?.investigation_id;
    if (!investigationId) return;
    feedbackMutation.mutate(
      { investigation_id: investigationId, approved },
      {
        onSuccess: data => {
          setFeedbackNote(
            `Feedback submitted (${data.approved ? 'Approved' : 'Rejected'}). Reward=${data.rl_update.reward}, training steps=${data.rl_update.learning_steps}.`,
          );
        },
      },
    );
  };

  const riskVariant = auditMutation.data?.final_risk || 'low';

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI Auditor Workbench"
        subtitle="Main orchestrator pipeline: Layer 1 → Layer 2 → Layer 3 → Layer 4 with CA feedback reinforcement."
      />

      <div className="grid gap-4 xl:grid-cols-[1.05fr_1fr]">
        <Card className="jarvis-panel">
          <CardHeader>
            <CardTitle>Transaction Payload · /audit_txn</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <textarea
              value={payloadText}
              onChange={e => setPayloadText(e.target.value)}
              rows={20}
              className="w-full rounded-md border border-slate-500/30 bg-slate-950/70 p-3 font-mono text-xs text-slate-100"
            />
            {jsonError && <p className="text-xs text-rose-300">{jsonError}</p>}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setPayloadText(JSON.stringify(SAMPLE_TXN, null, 2))}>
                Reset sample
              </Button>
              <Button onClick={runPipeline} disabled={auditMutation.isPending}>
                {auditMutation.isPending ? 'Running pipeline...' : 'Run Audit Pipeline'}
              </Button>
            </div>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Risk Decision</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {auditMutation.data ? (
                <>
                  <div className="flex items-center gap-2">
                    <Badge variant={riskVariant}>{auditMutation.data.final_risk}</Badge>
                    <span className="font-mono text-sm text-cyan-200">
                      Score {(Number(auditMutation.data.risk_score || 0) * 100).toFixed(1)}%
                    </span>
                  </div>
                  <p className="rounded-md border border-slate-600/50 bg-slate-900/60 p-3 text-sm leading-6">
                    {auditMutation.data.remark}
                  </p>
                </>
              ) : (
                <p className="text-sm text-slate-300">Run the pipeline to generate a risk decision.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>CA Override & RL Feedback</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex gap-2">
                <Button
                  className="flex-1"
                  onClick={() => sendFeedback(true)}
                  disabled={!auditMutation.data || feedbackMutation.isPending}
                >
                  Approve
                </Button>
                <Button
                  variant="destructive"
                  className="flex-1"
                  onClick={() => sendFeedback(false)}
                  disabled={!auditMutation.data || feedbackMutation.isPending}
                >
                  Reject
                </Button>
              </div>
              <p className="text-xs text-slate-300">
                Every click updates Layer 4 reinforcement learning (+10 approval / -5 rejection).
              </p>
              {feedbackNote && <p className="text-xs text-emerald-300">{feedbackNote}</p>}
            </CardContent>
          </Card>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Proof (Layer 1 formal evidence)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[360px] overflow-auto rounded-md bg-slate-950/80 p-3">
              <pre className="text-[11px] leading-5 text-slate-200">
                {JSON.stringify(auditMutation.data?.proof || {}, null, 2)}
              </pre>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Evidence Pack (Layer 4)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-[360px] overflow-auto rounded-md bg-slate-950/80 p-3">
              <pre className="text-[11px] leading-5 text-slate-200">
                {JSON.stringify(auditMutation.data?.evidence_pack || {}, null, 2)}
              </pre>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
