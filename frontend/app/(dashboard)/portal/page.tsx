'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import StatusBadge from '@/components/shared/StatusBadge';

interface PortalOverview {
  contacts: number;
  active_contacts: number;
  requests: number;
  open_requests: number;
  overdue_requests: number;
  due_next_7_days: number;
  received_pending_review: number;
  by_status: Record<string, number>;
  by_type: Record<string, number>;
}

interface PortalContact {
  id: string;
  client_id: string;
  client_name: string;
  name: string;
  email: string;
  phone?: string;
  role: string;
  access_status: string;
  last_login_at?: string;
}

interface PortalRequest {
  id: string;
  client_id: string;
  client_name: string;
  contact_id?: string;
  contact_name?: string;
  request_type: string;
  title: string;
  description?: string;
  due_date?: string;
  status: string;
  is_overdue: boolean;
  days_overdue: number;
  response_summary?: string;
}

const today = new Date().toISOString().slice(0, 10);
const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);

export default function PortalPage() {
  const [contactFilterClient, setContactFilterClient] = useState('');
  const [contactFilterStatus, setContactFilterStatus] = useState('');
  const [requestFilters, setRequestFilters] = useState({ status: 'requested,in_progress,received', client_id: '', request_type: '', due_to: nextWeek });
  const [contactForm, setContactForm] = useState({ client_id: '', name: '', email: '', phone: '', role: 'client_user' });
  const [requestForm, setRequestForm] = useState({
    client_id: '',
    contact_id: '',
    request_type: 'document',
    title: 'Upload monthly GST data',
    description: '',
    due_date: today,
  });

  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const overview = useQuery<PortalOverview>({ queryKey: ['portal-overview'], queryFn: () => api.get('/portal/overview').then(r => r.data) });
  const contacts = useQuery<PortalContact[]>({
    queryKey: ['portal-contacts', contactFilterClient, contactFilterStatus],
    queryFn: () => api.get('/portal/contacts', {
      params: {
        client_id: contactFilterClient || undefined,
        access_status: contactFilterStatus || undefined,
      },
    }).then(r => r.data),
  });
  const requests = useQuery<PortalRequest[]>({
    queryKey: ['portal-requests', requestFilters],
    queryFn: () => api.get('/portal/requests', {
      params: {
        status: requestFilters.status || undefined,
        client_id: requestFilters.client_id || undefined,
        request_type: requestFilters.request_type || undefined,
        due_to: requestFilters.due_to || undefined,
      },
    }).then(r => r.data),
  });

  const requestContacts = useMemo(() => {
    return (contacts.data || []).filter(contact => !requestForm.client_id || contact.client_id === requestForm.client_id);
  }, [contacts.data, requestForm.client_id]);

  async function refreshPortal() {
    await Promise.all([overview.refetch(), contacts.refetch(), requests.refetch()]);
  }

  async function createContact(event: FormEvent) {
    event.preventDefault();
    await api.post('/portal/contacts', contactForm);
    setContactForm({ ...contactForm, name: '', email: '', phone: '' });
    await refreshPortal();
  }

  async function createRequest(event: FormEvent) {
    event.preventDefault();
    await api.post('/portal/requests', {
      ...requestForm,
      contact_id: requestForm.contact_id || null,
      description: requestForm.description || null,
    });
    await refreshPortal();
  }

  async function updateRequest(item: PortalRequest, status: string) {
    await api.patch(`/portal/requests/${item.id}`, {
      status,
      response_summary: status === 'closed' ? 'Closed from office workspace.' : `Marked ${status} from portal workspace.`,
    });
    await refreshPortal();
  }

  const metrics = [
    ['Contacts', overview.data?.contacts || 0],
    ['Active contacts', overview.data?.active_contacts || 0],
    ['Open requests', overview.data?.open_requests || 0],
    ['Overdue', overview.data?.overdue_requests || 0],
    ['Due 7 days', overview.data?.due_next_7_days || 0],
    ['Pending review', overview.data?.received_pending_review || 0],
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-950">Client Portal</h1>
        <p className="text-sm text-slate-500">Client contacts, document requests, approvals, status visibility, and secure collaboration queue.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Request queue</h2>
              <p className="mt-1 text-xs text-slate-500">Track client asks by due date, request type, and response state.</p>
            </div>
            <StatusBadge value={requests.isLoading ? 'pending' : `${requests.data?.length || 0} requests`} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <select value={requestFilters.status} onChange={e => setRequestFilters({ ...requestFilters, status: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="requested,in_progress,received">Active</option>
              <option value="requested">Requested</option>
              <option value="in_progress">In progress</option>
              <option value="received">Received</option>
              <option value="approved,closed">Closed</option>
              <option value="">All</option>
            </select>
            <ClientSelect clients={clients.data || []} value={requestFilters.client_id} onChange={value => setRequestFilters({ ...requestFilters, client_id: value })} />
            <select value={requestFilters.request_type} onChange={e => setRequestFilters({ ...requestFilters, request_type: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All types</option>
              <option value="document">Document</option>
              <option value="approval">Approval</option>
              <option value="clarification">Clarification</option>
              <option value="payment">Payment</option>
            </select>
            <input type="date" value={requestFilters.due_to} onChange={e => setRequestFilters({ ...requestFilters, due_to: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" />
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Request</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Contact</th>
                  <th className="px-4 py-3">Due</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(requests.data || []).map(item => (
                  <tr key={item.id} className={`border-t border-slate-100 ${item.is_overdue ? 'bg-red-50' : ''}`}>
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-900">{item.title}</p>
                      <p className="text-xs text-slate-500">{item.request_type}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-600">{item.client_name}</td>
                    <td className="px-4 py-3 text-slate-600">{item.contact_name || '-'}</td>
                    <td className="px-4 py-3 text-slate-600">{item.due_date || '-'}{item.days_overdue ? ` (${item.days_overdue}d late)` : ''}</td>
                    <td className="px-4 py-3"><StatusBadge value={item.status} /></td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {item.status === 'requested' && <button onClick={() => updateRequest(item, 'in_progress')} className="rounded-md border border-slate-300 px-2 py-1 text-xs">Start</button>}
                        {item.status !== 'approved' && <button onClick={() => updateRequest(item, 'approved')} className="rounded-md border border-slate-300 px-2 py-1 text-xs">Approve</button>}
                        {!['closed', 'approved'].includes(item.status) && <button onClick={() => updateRequest(item, 'closed')} className="rounded-md bg-slate-950 px-2 py-1 text-xs text-white">Close</button>}
                      </div>
                    </td>
                  </tr>
                ))}
                {!requests.data?.length && !requests.isLoading && (
                  <tr className="border-t"><td colSpan={6} className="px-4 py-8 text-center text-sm text-slate-500">No portal requests match the filters.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="space-y-4">
          <form onSubmit={createContact} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Invite contact</h2>
            <div className="mt-3 space-y-3">
              <ClientSelect clients={clients.data || []} value={contactForm.client_id} onChange={value => setContactForm({ ...contactForm, client_id: value })} />
              <input required value={contactForm.name} onChange={e => setContactForm({ ...contactForm, name: e.target.value })} placeholder="Contact name" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <input required type="email" value={contactForm.email} onChange={e => setContactForm({ ...contactForm, email: e.target.value })} placeholder="Email" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <input value={contactForm.phone} onChange={e => setContactForm({ ...contactForm, phone: e.target.value })} placeholder="Phone" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Invite</button>
            </div>
          </form>

          <form onSubmit={createRequest} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Create request</h2>
            <div className="mt-3 space-y-3">
              <ClientSelect clients={clients.data || []} value={requestForm.client_id} onChange={value => setRequestForm({ ...requestForm, client_id: value, contact_id: '' })} />
              <select value={requestForm.contact_id} onChange={e => setRequestForm({ ...requestForm, contact_id: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
                <option value="">Any portal contact</option>
                {requestContacts.map(contact => <option key={contact.id} value={contact.id}>{contact.name} / {contact.client_name}</option>)}
              </select>
              <select value={requestForm.request_type} onChange={e => setRequestForm({ ...requestForm, request_type: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
                <option value="document">Document</option>
                <option value="approval">Approval</option>
                <option value="clarification">Clarification</option>
                <option value="payment">Payment</option>
              </select>
              <input required value={requestForm.title} onChange={e => setRequestForm({ ...requestForm, title: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <textarea value={requestForm.description} onChange={e => setRequestForm({ ...requestForm, description: e.target.value })} placeholder="Request details" className="h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <input type="date" value={requestForm.due_date} onChange={e => setRequestForm({ ...requestForm, due_date: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <button className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700">Send request</button>
            </div>
          </form>
        </section>
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Portal contacts</h2>
            <p className="mt-1 text-xs text-slate-500">Client-side users and access readiness.</p>
          </div>
          <div className="grid gap-2 md:grid-cols-2">
            <ClientSelect clients={clients.data || []} value={contactFilterClient} onChange={setContactFilterClient} />
            <select value={contactFilterStatus} onChange={e => setContactFilterStatus(e.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All statuses</option>
              <option value="invited">Invited</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
            </select>
          </div>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(contacts.data || []).map(contact => (
            <div key={contact.id} className="rounded-md border border-slate-200 p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-semibold text-slate-900">{contact.name}</p>
                  <p className="text-xs text-slate-500">{contact.client_name}</p>
                </div>
                <StatusBadge value={contact.access_status} />
              </div>
              <p className="mt-2 text-xs text-slate-600">{contact.email}</p>
              <p className="mt-1 text-xs text-slate-500">{contact.phone || '-'} / {contact.role}</p>
            </div>
          ))}
          {!contacts.data?.length && !contacts.isLoading && <p className="py-8 text-sm text-slate-500">No contacts match the filters.</p>}
        </div>
      </section>
    </div>
  );
}
