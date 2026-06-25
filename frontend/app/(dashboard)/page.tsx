'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { ArrowRight, Bot, Building2, ClipboardCheck, ShieldAlert, Sparkles } from 'lucide-react';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientTable from '@/components/clients/ClientTable';

const WORKSTREAMS = [
  { title: 'Practice CRM', detail: 'Clients, contacts, groups, assignments, entity records', status: 'Live' },
  { title: 'Job & Task OS', detail: 'Recurring jobs, checklists, review stages, workload board', status: 'Live' },
  { title: 'Compliance Calendar', detail: 'Applicability, due dates, risk, reminders, sign-off', status: 'Live' },
  { title: 'Document Vault', detail: 'Uploads, OCR, metadata, evidence links, reviewer notes', status: 'Live' },
  { title: 'Tally & Excel Intake', detail: 'CSV, local Tally HTTP connector, normalized vouchers', status: 'Live' },
  { title: 'GST Reconciliation', detail: 'Books vs portal variance, exposure, vendor follow-ups', status: 'Live' },
  { title: 'Billing & Collections', detail: 'Fee plans, invoices, ageing, realization reports', status: 'Live' },
  { title: 'Client Portal', detail: 'Requests, uploads, approvals, status, secure messages', status: 'Live' },
  { title: 'Team & HR', detail: 'Attendance, capacity, ownership, utilization signals', status: 'Live' },
  { title: 'Credential Vault', detail: 'DSC, portal credentials, expiry, rotation tracking', status: 'Live' },
  { title: 'Reports', detail: 'Saved views, partner metrics, workload, collections', status: 'Live' },
];

const AI_MODULES = [
  'Exception Autopilot',
  'Notice Drafter',
  'Audit Papers',
  'Invoice Fraud Scanner',
  'NL Query',
  'MSME 43B(h)',
  'Drawing Power',
  'CA Certificates',
];

export default function DashboardPage() {
  const router = useRouter();
  const { data: clients = [], isLoading } = useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  });

  const red = clients.filter(c => c.health_score < 50).length;
  const amber = clients.filter(c => c.health_score >= 50 && c.health_score < 75).length;
  const green = clients.filter(c => c.health_score >= 75).length;

  return (
    <div className="space-y-6">
      <div className="premium-panel overflow-hidden rounded-2xl p-5 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-sky-700">Partner command center</p>
            <h1 className="mt-1 max-w-4xl text-2xl font-semibold text-slate-950 sm:text-3xl">
              CA practice operations, compliance, and AI review in one desk
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600">
              Built to cover the practice management depth of CA office tools and the execution speed of AI-first CA assistants.
            </p>
          </div>
          <div className="flex gap-2">
            <button onClick={() => router.push('/autopilot')} className="liquid-button flex h-10 items-center gap-2 rounded-xl px-3 text-sm font-medium text-white transition">
              <Bot className="h-4 w-4" />
              Exceptions
            </button>
            <button onClick={() => router.push('/clients')} className="flex h-10 items-center gap-2 rounded-xl border border-white/80 bg-white/80 px-3 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-white">
              <Building2 className="h-4 w-4" />
              Clients
            </button>
          </div>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {[
          { label: 'Total Clients', value: clients.length, color: 'text-slate-950', Icon: Building2 },
          { label: 'High Risk', value: red, color: 'text-rose-600', Icon: ShieldAlert },
          { label: 'Needs Attention', value: amber, color: 'text-amber-600', Icon: ClipboardCheck },
          { label: 'Healthy', value: green, color: 'text-emerald-600', Icon: Sparkles },
        ].map(card => (
          <div key={card.label} className="apple-surface rounded-2xl p-4">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium text-slate-500">{card.label}</p>
              <span className="grid h-8 w-8 place-items-center rounded-xl bg-white shadow-sm ring-1 ring-slate-200/80">
                <card.Icon className="h-4 w-4 text-slate-500" />
              </span>
            </div>
            <p className={`mt-1 text-2xl font-semibold ${card.color}`}>{card.value}</p>
          </div>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.25fr_.75fr]">
        <section className="apple-surface rounded-2xl p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Practice suite coverage</h2>
              <p className="text-xs text-slate-500">Competitor-parity scope mapped to CA Copilot modules.</p>
            </div>
            <span className="rounded-full bg-sky-50 px-2.5 py-1 text-xs font-semibold text-sky-700 ring-1 ring-sky-100">20+ modules</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {WORKSTREAMS.map(item => (
              <div key={item.title} className="rounded-xl border border-slate-200/70 bg-white/72 p-3 shadow-sm transition hover:-translate-y-0.5 hover:bg-white hover:shadow-md">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-900">{item.title}</h3>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                    item.status === 'Live' ? 'bg-green-50 text-green-700' :
                    item.status === 'Build next' ? 'bg-amber-50 text-amber-700' :
                    'bg-slate-100 text-slate-600'
                  }`}>
                    {item.status}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-slate-600">{item.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="apple-surface rounded-2xl p-4">
          <h2 className="text-sm font-semibold text-slate-900">AI execution layer</h2>
          <p className="mt-1 text-xs text-slate-500">Review-ready deliverables and evidence-backed decisions.</p>
          <div className="mt-4 space-y-2">
            {AI_MODULES.map((module, index) => (
              <div key={module} className="group flex items-center gap-3 rounded-xl border border-slate-200/70 bg-white/70 px-3 py-2 shadow-sm transition hover:bg-white">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-slate-950 text-xs font-semibold text-white shadow-sm">
                  {index + 1}
                </span>
                <span className="text-sm font-medium text-slate-700">{module}</span>
                <ArrowRight className="ml-auto h-4 w-4 text-slate-300 transition group-hover:translate-x-0.5 group-hover:text-slate-500" />
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="apple-surface rounded-2xl p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">Client portfolio</h2>
        {isLoading ? (
          <p className="text-sm text-slate-400">Loading...</p>
        ) : (
          <ClientTable
            clients={clients}
            onClientClick={c => router.push(`/clients/${c.id}`)}
          />
        )}
      </div>
    </div>
  );
}
