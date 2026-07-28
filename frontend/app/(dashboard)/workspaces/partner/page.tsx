'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import RoleShell from '@/components/layout/RoleShell';
import { api } from '@/lib/api';
import { Client, User } from '@/types';

export default function PartnerWorkspacePage() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState('');

  const clients = useQuery<Client[]>({
    queryKey: ['partner-clients'],
    queryFn: () => api.get('/clients', { params: { limit: 200 } }).then(r => r.data),
  });
  const users = useQuery<User[]>({
    queryKey: ['partner-users'],
    queryFn: () => api.get('/users').then(r => r.data),
  });

  const cas = useMemo(
    () => (users.data || []).filter(user => user.role === 'manager' || user.role === 'partner'),
    [users.data],
  );

  const assign = useMutation({
    mutationFn: ({ clientId, assigned_ca_user_id }: { clientId: string; assigned_ca_user_id: string | null }) =>
      api.post(`/clients/${clientId}/assign`, { assigned_ca_user_id }).then(r => r.data),
    onSuccess: () => {
      setMessage('Client assignment updated.');
      queryClient.invalidateQueries({ queryKey: ['partner-clients'] });
    },
    onError: (err: Error) => setMessage(err.message || 'Assignment failed'),
  });

  const unassigned = (clients.data || []).filter(client => !client.assigned_ca_user_id).length;

  return (
    <RoleShell
      title="Firm Head Command Deck"
      subtitle="Firm-wide oversight, CA staffing, and partner-only controls. Assign every client to a responsible CA."
      accent="partner"
      allowedFeatures={[
        'command_center',
        'clients_crm',
        'team_attendance',
        'billing_collections',
        'benchmarking',
        'profitability_audit',
        'dsc_password_vault',
        'peer_review_qc',
        'ai_audit_orchestrator',
      ]}
    >
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-stone-300 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Clients</p>
          <p className="mt-2 text-3xl font-semibold text-stone-950">{clients.data?.length || 0}</p>
        </div>
        <div className="rounded-xl border border-stone-300 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Active CAs</p>
          <p className="mt-2 text-3xl font-semibold text-stone-950">{cas.length}</p>
        </div>
        <div className="rounded-xl border border-stone-300 bg-white p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Unassigned</p>
          <p className="mt-2 text-3xl font-semibold text-amber-800">{unassigned}</p>
        </div>
      </div>

      <section className="mt-6 rounded-xl border border-stone-300 bg-white p-4">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <div>
            <h2 className="text-lg font-semibold text-stone-950">Assign clients to CA</h2>
            <p className="text-sm text-stone-600">Only Firm Head can change ownership. Managers then see their assigned book.</p>
          </div>
          {message && <p className="text-xs font-medium text-teal-800">{message}</p>}
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="border-b border-stone-300 text-xs uppercase tracking-[0.12em] text-stone-500">
              <tr>
                <th className="px-2 py-2">Client</th>
                <th className="px-2 py-2">Health</th>
                <th className="px-2 py-2">Assigned CA</th>
                <th className="px-2 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {(clients.data || []).map(client => (
                <tr key={client.id} className="border-b border-stone-200">
                  <td className="px-2 py-3">
                    <p className="font-medium text-stone-950">{client.name}</p>
                    <p className="text-xs text-stone-500">{client.gstin || 'No GSTIN'}</p>
                  </td>
                  <td className="px-2 py-3 text-stone-800">{client.health_score}</td>
                  <td className="px-2 py-3 text-stone-700">{client.assigned_ca_email || 'Unassigned'}</td>
                  <td className="px-2 py-3">
                    <select
                      className="rounded-md border border-stone-300 bg-stone-50 px-2 py-1.5 text-xs text-stone-900"
                      value={client.assigned_ca_user_id || ''}
                      onChange={event =>
                        assign.mutate({
                          clientId: client.id,
                          assigned_ca_user_id: event.target.value || null,
                        })
                      }
                    >
                      <option value="">Unassigned</option>
                      {cas.map(ca => (
                        <option key={ca.id} value={ca.id}>
                          {ca.email} ({ca.role})
                        </option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </RoleShell>
  );
}
