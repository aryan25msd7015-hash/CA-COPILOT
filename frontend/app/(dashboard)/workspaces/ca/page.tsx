'use client';

import { useQuery } from '@tanstack/react-query';
import RoleShell from '@/components/layout/RoleShell';
import { api } from '@/lib/api';
import { Client } from '@/types';

export default function CAWorkspacePage() {
  const clients = useQuery<Client[]>({
    queryKey: ['ca-clients'],
    queryFn: () => api.get('/clients', { params: { mine_only: true, limit: 200 } }).then(r => r.data),
  });
  const anomalies = useQuery({
    queryKey: ['ca-anomaly-summary'],
    queryFn: () => api.get('/anomalies/summary').then(r => r.data),
  });

  return (
    <RoleShell
      title="CA Manager Desk"
      subtitle="Your assigned client book, review queue, and sign-off work. No firm financial or vault access."
      accent="ca"
      expectedRole="manager"
      domainBound
      allowedFeatures={[
        'workspace_ca',
        'clients_crm',
        'audit_papers',
        'anomalies',
        'notice_drafter',
        'gst_reconciliation',
        'query_observation_ledger',
        'exception_autopilot',
        'causal_risk_layer3',
        'logic_audit_layer1',
      ]}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-stone-300 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Assigned clients</p>
          <p className="mt-2 text-3xl font-semibold text-stone-950">{clients.data?.length || 0}</p>
        </div>
        <div className="rounded-xl border border-stone-300 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Open anomalies</p>
          <p className="mt-2 text-3xl font-semibold text-stone-950">{anomalies.data?.open?.count || 0}</p>
        </div>
        <div className="rounded-xl border border-stone-300 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Needs follow-up</p>
          <p className="mt-2 text-3xl font-semibold text-amber-800">{anomalies.data?.needs_followup?.count || 0}</p>
        </div>
      </div>

      <section className="mt-6 rounded-xl border border-stone-300 bg-white p-4">
        <h2 className="text-lg font-semibold text-stone-950">Assigned book</h2>
        <p className="text-sm text-stone-600">Only clients assigned by Firm Head appear here.</p>
        <div className="mt-4 space-y-2">
          {(clients.data || []).map(client => (
            <div key={client.id} className="flex items-center justify-between rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
              <div>
                <p className="font-medium text-stone-950">{client.name}</p>
                <p className="text-xs text-stone-500">{client.gstin || 'No GSTIN'}</p>
              </div>
              <span className="rounded-full border border-stone-300 bg-white px-2 py-0.5 text-xs font-medium text-stone-800">
                Health {client.health_score}
              </span>
            </div>
          ))}
          {!clients.data?.length && (
            <p className="text-sm text-stone-600">No clients assigned yet. Ask Firm Head to assign ownership.</p>
          )}
        </div>
      </section>
    </RoleShell>
  );
}
