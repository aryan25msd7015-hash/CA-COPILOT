'use client';

import { useQuery } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { ArrowRight, ArrowUpRight, Bot, Building2, ClipboardCheck, ShieldAlert, Sparkles, TrendingUp, Zap } from 'lucide-react';
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
  { name: 'Exception Autopilot', href: '/autopilot', tone: 'cyan' },
  { name: 'Notice Drafter', href: '/notices', tone: 'violet' },
  { name: 'Audit Papers', href: '/audit', tone: 'cyan' },
  { name: 'Invoice Fraud Scanner', href: '/invoices', tone: 'rose' },
  { name: 'NL Query', href: '/query', tone: 'violet' },
  { name: 'MSME 43B(h)', href: '/msme', tone: 'amber' },
  { name: 'Drawing Power', href: '/drawing-power', tone: 'emerald' },
  { name: 'CA Certificates', href: '/certificates', tone: 'cyan' },
];

const TONE_MAP: Record<string, { chip: string; ring: string; dot: string }> = {
  cyan:    { chip: 'chip chip-cyan',    ring: 'ring-cyan-400/40',    dot: 'bg-cyan-400' },
  violet:  { chip: 'chip chip-violet',  ring: 'ring-violet-400/40',  dot: 'bg-violet-400' },
  rose:    { chip: 'chip chip-rose',    ring: 'ring-rose-400/40',    dot: 'bg-rose-400' },
  amber:   { chip: 'chip chip-amber',   ring: 'ring-amber-400/40',   dot: 'bg-amber-400' },
  emerald: { chip: 'chip chip-emerald', ring: 'ring-emerald-400/40', dot: 'bg-emerald-400' },
};

export default function DashboardPage() {
  const router = useRouter();
  const { data: clients = [], isLoading } = useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  });

  const red = clients.filter(c => c.health_score < 50).length;
  const amber = clients.filter(c => c.health_score >= 50 && c.health_score < 75).length;
  const green = clients.filter(c => c.health_score >= 75).length;
  const total = clients.length;
  const healthyPct = total > 0 ? Math.round((green / total) * 100) : 0;

  const stats = [
    { label: 'Total Clients',   value: total, tone: 'text-fg-0',       icon: Building2,      accent: 'from-cyan-400/25 to-transparent' },
    { label: 'High Risk',       value: red,   tone: 'text-rose-300',   icon: ShieldAlert,    accent: 'from-rose-500/25 to-transparent' },
    { label: 'Needs Attention', value: amber, tone: 'text-amber-300',  icon: ClipboardCheck, accent: 'from-amber-500/25 to-transparent' },
    { label: 'Healthy',         value: green, tone: 'text-emerald-300',icon: Sparkles,       accent: 'from-emerald-500/25 to-transparent' },
  ] as const;

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* HERO / COMMAND HEADER */}
      <div className="jarvis-panel premium-panel overflow-hidden rounded-2xl p-6 sm:p-7">
        <div className="relative flex flex-wrap items-start justify-between gap-6">
          <div className="max-w-3xl">
            <div className="flex items-center gap-2">
              <span className="motion-blink inline-block h-1.5 w-1.5 rounded-full bg-cyan-400" />
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.32em] text-cyan-signal">
                Partner Command Center · Sector 01
              </p>
            </div>
            <h1 className="mt-3 font-display text-3xl font-semibold leading-[1.1] text-fg-0 sm:text-4xl">
              CA practice operations, compliance and <span className="text-cyan-signal">AI review</span>
              <span className="text-violet-signal"> · one terminal</span>
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-fg-2">
              Built to cover the depth of traditional CA suites and the execution speed of AI-first assistants.
              Every exception, deadline and follow-up piped through a single review queue.
            </p>

            <div className="mt-5 flex flex-wrap gap-2">
              <button
                onClick={() => router.push('/autopilot')}
                data-testid="hero-exceptions-btn"
                className="liquid-button flex h-10 items-center gap-2 rounded-xl px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40"
              >
                <Bot className="h-4 w-4" />
                Open Exceptions
                <ArrowUpRight className="h-4 w-4 opacity-80" />
              </button>
              <button
                onClick={() => router.push('/clients')}
                data-testid="hero-clients-btn"
                className="ghost-button flex h-10 items-center gap-2 rounded-xl px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40"
              >
                <Building2 className="h-4 w-4" />
                Clients CRM
              </button>
              <button
                onClick={() => router.push('/query')}
                data-testid="hero-query-btn"
                className="neon-outline flex h-10 items-center gap-2 rounded-xl px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40"
              >
                <Zap className="h-4 w-4" />
                Ask CA Copilot
              </button>
            </div>
          </div>

          {/* Health index dial */}
          <div className="relative shrink-0" data-testid="health-dial">
            <div className="hud-corners relative grid h-40 w-40 place-items-center rounded-2xl border border-line bg-[rgba(6,11,26,0.7)] p-3">
              <svg viewBox="0 0 120 120" className="h-full w-full -rotate-90">
                <circle cx="60" cy="60" r="52" fill="none" stroke="rgba(148,163,214,0.14)" strokeWidth="8" />
                <circle
                  cx="60" cy="60" r="52" fill="none"
                  stroke="url(#dial)" strokeWidth="8" strokeLinecap="round"
                  strokeDasharray={`${(healthyPct / 100) * 326.7} 326.7`}
                />
                <defs>
                  <linearGradient id="dial" x1="0" y1="0" x2="1" y2="1">
                    <stop offset="0%" stopColor="#22d3ee" />
                    <stop offset="100%" stopColor="#a78bfa" />
                  </linearGradient>
                </defs>
              </svg>
              <div className="absolute inset-0 grid place-items-center text-center">
                <div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.28em] text-fg-3">Portfolio</div>
                  <div className="font-display text-3xl font-semibold text-fg-0">{healthyPct}<span className="text-lg text-fg-2">%</span></div>
                  <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-cyan-signal">Healthy</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* STAT BAND */}
      <div className="grid gap-4 md:grid-cols-4" data-testid="stat-band">
        {stats.map((card, i) => (
          <div
            key={card.label}
            className="hud-panel group relative overflow-hidden rounded-2xl p-4 transition hover:-translate-y-0.5 hover:border-cyan-400/40"
            data-testid={`stat-card-${card.label.toLowerCase().replace(/\s+/g,'-')}`}
          >
            <div className={`pointer-events-none absolute inset-0 bg-gradient-to-br ${card.accent} opacity-70`} />
            <div className="relative">
              <div className="flex items-center justify-between">
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.24em] text-fg-3">
                  {String(i + 1).padStart(2, '0')} · {card.label}
                </p>
                <span className="grid h-8 w-8 place-items-center rounded-lg border border-line bg-black/30">
                  <card.icon className="h-4 w-4 text-fg-2" />
                </span>
              </div>
              <div className="mt-2 flex items-end gap-2">
                <p className={`font-display font-mono-num text-4xl font-semibold ${card.tone}`}>
                  {String(card.value).padStart(2, '0')}
                </p>
                <span className="mb-1.5 flex items-center gap-1 font-mono text-[10px] text-fg-3">
                  <TrendingUp className="h-3 w-3 text-emerald-400" /> vs 7d
                </span>
              </div>
              {/* Sparkline placeholder */}
              <svg viewBox="0 0 100 20" className="mt-2 h-6 w-full">
                <polyline
                  fill="none"
                  stroke="url(#spark-grad)"
                  strokeWidth="1.5"
                  points={`0,${14 - (i * 2)} 15,${10 + i} 30,${6 - i} 45,${12 - i} 60,${5 + (i % 2)} 75,${9} 90,${4 + i} 100,${8}`}
                />
                <defs>
                  <linearGradient id="spark-grad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor="#22d3ee" stopOpacity="0.9" />
                    <stop offset="100%" stopColor="#a78bfa" stopOpacity="0.9" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
          </div>
        ))}
      </div>

      {/* PRACTICE SUITE + AI EXECUTION */}
      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <section className="hud-panel rounded-2xl p-5" data-testid="practice-suite-card">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
                MODULE MATRIX
              </p>
              <h2 className="mt-1 font-display text-lg font-semibold text-fg">Practice suite coverage</h2>
              <p className="mt-0.5 text-xs text-fg-2">Competitor-parity scope mapped to CA Copilot modules.</p>
            </div>
            <span className="chip chip-cyan">20+ modules · Live</span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {WORKSTREAMS.map((item, i) => (
              <div
                key={item.title}
                className="group relative overflow-hidden rounded-xl border border-line bg-[rgba(9,14,32,0.55)] p-3 transition hover:-translate-y-0.5 hover:border-cyan-400/40 hover:bg-[rgba(15,22,45,0.7)]"
              >
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent opacity-0 transition group-hover:opacity-100" />
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] text-fg-3">M-{String(i + 1).padStart(2, '0')}</span>
                    <h3 className="text-sm font-semibold text-fg">{item.title}</h3>
                  </div>
                  <span className="chip chip-emerald">{item.status}</span>
                </div>
                <p className="mt-1 text-xs leading-5 text-fg-2">{item.detail}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="hud-panel rounded-2xl p-5" data-testid="ai-modules-card">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-violet-signal">
            EXECUTION LAYER
          </p>
          <h2 className="mt-1 font-display text-lg font-semibold text-fg">AI review pipeline</h2>
          <p className="mt-0.5 text-xs text-fg-2">Review-ready deliverables and evidence-backed decisions.</p>

          <div className="mt-4 space-y-2">
            {AI_MODULES.map((mod, index) => {
              const t = TONE_MAP[mod.tone];
              return (
                <button
                  key={mod.name}
                  onClick={() => router.push(mod.href)}
                  data-testid={`ai-module-${mod.name.toLowerCase().replace(/\s+/g,'-')}`}
                  className={`group flex w-full items-center gap-3 rounded-xl border border-line bg-[rgba(9,14,32,0.55)] px-3 py-2.5 text-left transition hover:-translate-y-0.5 hover:border-cyan-400/40 hover:bg-[rgba(15,22,45,0.72)] focus-visible:outline-none focus-visible:ring-2 ${t.ring}`}
                >
                  <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-lg font-mono text-[11px] font-semibold ${t.chip}`}>
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="flex-1">
                    <span className="block text-sm font-medium text-fg">{mod.name}</span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">
                      <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${t.dot}`} /> Online
                    </span>
                  </span>
                  <ArrowRight className="h-4 w-4 text-fg-3 transition group-hover:translate-x-0.5 group-hover:text-cyan-300" />
                </button>
              );
            })}
          </div>
        </section>
      </div>

      {/* CLIENT PORTFOLIO */}
      <div className="hud-panel rounded-2xl p-5" data-testid="client-portfolio-card">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
              CLIENT PORTFOLIO · LIVE FEED
            </p>
            <h2 className="mt-1 font-display text-lg font-semibold text-fg">Client health & GSTIN registry</h2>
          </div>
          <span className="chip">{isLoading ? 'Loading' : `${total} records`}</span>
        </div>
        {isLoading ? (
          <div className="flex items-center gap-3 text-sm text-fg-2">
            <span className="ring-loader" />
            <span className="font-mono text-[11px] uppercase tracking-[0.22em]">Streaming records…</span>
          </div>
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
