'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { api } from '@/lib/api';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

interface RiskRow {
  id: string;
  client_name: string;
  score: number;
  tier: string;
  drivers: { factor: string; weight: number }[];
  computed_at?: string;
}

const columns: ColDef<RiskRow>[] = [
  { field: 'client_name', headerName: 'Client', minWidth: 180 },
  { field: 'score', headerName: 'Score' },
  { field: 'tier', headerName: 'Tier', cellRenderer: (p: { value?: string }) => <StatusBadge value={p.value} /> },
  {
    field: 'drivers',
    headerName: 'Drivers',
    minWidth: 260,
    valueFormatter: p => (p.value || []).map((d: { factor: string; weight: number }) => `${d.factor}:${d.weight}`).join(' · ') || '-',
  },
  { field: 'computed_at', headerName: 'Computed', minWidth: 180 },
];

export default function RiskScoresPage() {
  const qc = useQueryClient();
  const rows = useQuery<RiskRow[]>({
    queryKey: ['risk-scores'],
    queryFn: () => api.get('/practice-gaps/risk-scores').then(r => r.data),
  });
  const recompute = useMutation({
    mutationFn: () => api.post('/practice-gaps/risk-scores/recompute'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['risk-scores'] }),
  });

  return (
    <div className="space-y-5">
      <PageHeader
        title="Client Risk Scoring"
        subtitle="Combines anomalies, overdue compliance, and billing outstanding into a single engagement risk score."
      />
      <div className="flex gap-3">
        <button
          onClick={() => recompute.mutate()}
          className="rounded-lg bg-cyan-600 px-3 py-2 text-sm text-white disabled:opacity-50"
          disabled={recompute.isPending}
        >
          Recompute scores
        </button>
      </div>
      <DataGrid rows={rows.data || []} columns={columns} />
    </div>
  );
}
