'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { clearPortalSession, getPortalProfile, portalGet } from '@/lib/portalAuth';

interface PortalMe {
  contact: { name: string; email: string };
  client: { name: string };
  features: string[];
}

export default function ClientPortalHomePage() {
  const router = useRouter();
  const profile = getPortalProfile<{ contact: { name: string }; client: { name: string } }>();
  const [me, setMe] = useState<PortalMe | null>(null);
  const [deadlines, setDeadlines] = useState<Record<string, unknown>[]>([]);
  const [invoices, setInvoices] = useState<Record<string, unknown>[]>([]);
  const [documents, setDocuments] = useState<Record<string, unknown>[]>([]);
  const [requests, setRequests] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      try {
        const [meRes, dl, inv, docs, reqs] = await Promise.all([
          portalGet<PortalMe>('/client-portal/me'),
          portalGet<Record<string, unknown>[]>('/client-portal/deadlines'),
          portalGet<Record<string, unknown>[]>('/client-portal/invoices'),
          portalGet<Record<string, unknown>[]>('/client-portal/documents'),
          portalGet<Record<string, unknown>[]>('/client-portal/requests'),
        ]);
        setMe(meRes);
        setDeadlines(dl);
        setInvoices(inv);
        setDocuments(docs);
        setRequests(reqs);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load portal');
      }
    }
    void load();
  }, []);

  function logout() {
    clearPortalSession();
    router.replace('/client-portal/login');
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-10">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-cyan-300">Client portal</p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-white">
            {me?.client.name || profile?.client?.name || 'Your workspace'}
          </h1>
          <p className="mt-1 text-sm text-slate-300">
            Signed in as {me?.contact.name || profile?.contact?.name || 'client'} — own data only.
          </p>
        </div>
        <button onClick={logout} className="rounded-lg border border-white/20 px-3 py-2 text-sm text-slate-200">
          Sign out
        </button>
      </header>

      {error && <p className="mb-4 text-sm text-rose-300">{error}</p>}

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Deadlines" rows={deadlines} fields={['title', 'due_date', 'status']} />
        <Section title="Invoices" rows={invoices} fields={['invoice_no', 'total', 'outstanding', 'status']} />
        <Section title="Documents" rows={documents} fields={['filename', 'doc_type', 'created_at']} />
        <Section title="Requests" rows={requests} fields={['title', 'request_type', 'due_date', 'status']} />
      </div>
    </div>
  );
}

function Section({
  title,
  rows,
  fields,
}: {
  title: string;
  rows: Record<string, unknown>[];
  fields: string[];
}) {
  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-cyan-200">{title}</h2>
      <ul className="mt-3 space-y-2">
        {rows.slice(0, 8).map((row, idx) => (
          <li key={String(row.id || idx)} className="rounded-lg border border-white/5 bg-black/20 px-3 py-2 text-sm text-slate-200">
            {fields.map(f => String(row[f] ?? '—')).join(' · ')}
          </li>
        ))}
        {!rows.length && <li className="text-sm text-slate-500">Nothing here yet.</li>}
      </ul>
    </section>
  );
}
