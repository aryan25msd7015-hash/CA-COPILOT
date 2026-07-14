'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle, ArrowUpRight, CheckCircle2, Clock, Loader2, Mail, Radio, Send, XCircle,
} from 'lucide-react';
import { api } from '@/lib/api';

interface EmailRecent {
  id: string;
  resend_message_id: string;
  template: string;
  recipient: string;
  subject: string;
  status: string;
  dry_run: boolean;
  created_at: string;
  updated_at: string;
  tags?: Record<string, string>;
}

interface EmailConfig {
  provider: string;
  dry_run: boolean;
  from: string;
  webhook_configured: boolean;
  preview_stub?: boolean;
}

const TEMPLATES = [
  'password_reset', 'email_verification', 'user_invitation',
  'invoice_sent', 'payment_received', 'invoice_overdue',
  'subscription_activated', 'subscription_cancelled',
  'document_request', 'portal_invite', 'report_ready',
];

const STATUS_CHIP: Record<string, string> = {
  delivered: 'chip chip-emerald',
  sent: 'chip chip-cyan',
  queued: 'chip',
  dry_run: 'chip chip-violet',
  bounced: 'chip chip-rose',
  complained: 'chip chip-rose',
  failed: 'chip chip-rose',
  delayed: 'chip chip-amber',
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  delivered: <CheckCircle2 className="h-3 w-3" />,
  sent: <Send className="h-3 w-3" />,
  bounced: <XCircle className="h-3 w-3" />,
  complained: <AlertTriangle className="h-3 w-3" />,
  failed: <XCircle className="h-3 w-3" />,
  delayed: <Clock className="h-3 w-3" />,
  queued: <Clock className="h-3 w-3" />,
};

export default function EmailSignalsTab() {
  const qc = useQueryClient();
  const [flash, setFlash] = useState<{ kind: 'ok' | 'err'; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ to: '', template: 'invoice_sent' });

  const config = useQuery<EmailConfig>({ queryKey: ['email-config'], queryFn: () => api.get('/email/config').then(r => r.data) });
  const recent = useQuery<EmailRecent[]>({ queryKey: ['email-recent'], queryFn: () => api.get('/email/recent').then(r => r.data) });

  async function testSend(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFlash(null);
    try {
      const res = await api.post('/email/test-send', {
        to: form.to || 'test@example.com',
        template: form.template,
        cta_url: 'https://cacopilot.example.com/dashboard',
      });
      setFlash({
        kind: 'ok',
        msg: res.data.dry_run
          ? `Dry-run · payload logged (id ${res.data.id}) — flip RESEND_DRY_RUN=false to send.`
          : `Sent · ${res.data.subject}`,
      });
      qc.invalidateQueries({ queryKey: ['email-recent'] });
    } catch (err: unknown) {
      setFlash({ kind: 'err', msg: (err as { response?: { data?: { detail?: string } } }).response?.data?.detail || (err as Error).message });
    } finally {
      setBusy(false);
    }
  }

  const dryRun = config.data?.dry_run ?? true;

  return (
    <div className="space-y-5" data-testid="email-signals-tab">
      {/* GATEWAY HEALTH */}
      <div className="hud-panel hud-corners flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
        <div className="flex items-center gap-3">
          <span className={`grid h-10 w-10 place-items-center rounded-xl border ${
            dryRun ? 'border-amber-400/50 bg-amber-500/10' : 'border-emerald-400/50 bg-emerald-500/10'
          }`}>
            <Mail className={`h-4 w-4 ${dryRun ? 'text-amber-300' : 'text-emerald-300'}`} />
          </span>
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
              GATEWAY · RESEND · TRANSACTIONAL
            </p>
            <p className="mt-0.5 text-sm font-medium text-fg">
              {dryRun
                ? 'Dry-run mode — payloads are logged, no real emails go out. Swap the API key + set RESEND_DRY_RUN=false to launch.'
                : 'Live delivery · Resend'}
            </p>
            <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">
              From · {config.data?.from || 'CA Copilot <onboarding@resend.dev>'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`chip ${dryRun ? 'chip-amber' : 'chip-emerald'}`}>
            {dryRun ? 'Dry-run' : 'Live'}
          </span>
          <span className={`chip ${config.data?.webhook_configured ? 'chip-cyan' : 'chip-amber'}`}>
            Webhook {config.data?.webhook_configured ? 'ok' : 'pending'}
          </span>
          <span className="chip chip-violet">{TEMPLATES.length} templates</span>
        </div>
      </div>

      {flash && (
        <div
          data-testid="email-flash"
          className={`hud-panel motion-pop flex items-start gap-3 rounded-xl border-l-4 p-3 ${
            flash.kind === 'ok' ? 'border-l-emerald-400 text-emerald-200' : 'border-l-rose-400 text-rose-200'
          }`}
        >
          {flash.kind === 'ok' ? <CheckCircle2 className="mt-0.5 h-4 w-4" /> : <XCircle className="mt-0.5 h-4 w-4" />}
          <span className="font-mono text-xs">{flash.msg}</span>
        </div>
      )}

      {/* TEST SEND */}
      <section className="hud-panel rounded-2xl p-5" data-testid="email-test-send-card">
        <div className="mb-3">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
            LIVE FIRE · TEST SEND
          </p>
          <h3 className="mt-1 font-display text-lg font-semibold text-fg">Fire any HUD template</h3>
          <p className="mt-0.5 text-xs text-fg-2">Renders the exact template used in production. In dry-run mode the payload is logged instead of sent.</p>
        </div>
        <form onSubmit={testSend} className="grid gap-3 md:grid-cols-6">
          <label className="flex flex-col gap-1 md:col-span-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Recipient</span>
            <input
              type="email"
              value={form.to}
              onChange={e => setForm({ ...form, to: e.target.value })}
              placeholder="you@example.com"
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="email-to"
            />
          </label>
          <label className="flex flex-col gap-1 md:col-span-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Template</span>
            <select
              value={form.template}
              onChange={e => setForm({ ...form, template: e.target.value })}
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="email-template"
            >
              {TEMPLATES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <div className="md:col-span-6">
            <button
              type="submit"
              disabled={busy}
              data-testid="email-test-btn"
              className="liquid-button flex h-10 items-center gap-2 rounded-xl px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:opacity-60"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Fire template
            </button>
          </div>
        </form>
      </section>

      {/* RECENT ACTIVITY */}
      <section className="hud-panel rounded-2xl p-5" data-testid="email-recent-card">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
              FEED · RECENT SIGNALS
            </p>
            <h3 className="mt-1 font-display text-lg font-semibold text-fg">Last 50 outbound signals</h3>
          </div>
          <span className="chip">
            <Radio className="motion-blink h-3 w-3" /> {recent.data?.length || 0}
          </span>
        </div>

        {recent.isLoading && (
          <div className="flex items-center gap-3 text-sm text-fg-2">
            <span className="ring-loader" />
            <span className="font-mono text-[11px] uppercase tracking-[0.22em]">Streaming feed…</span>
          </div>
        )}

        <div className="overflow-hidden rounded-xl border border-line">
          <table className="w-full text-sm">
            <thead className="bg-[rgba(6,11,26,0.7)]">
              <tr className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">
                <th className="px-3 py-2 text-left">When</th>
                <th className="px-3 py-2 text-left">Template</th>
                <th className="px-3 py-2 text-left">Recipient</th>
                <th className="px-3 py-2 text-left">Subject</th>
                <th className="px-3 py-2 text-left">Status</th>
              </tr>
            </thead>
            <tbody>
              {(recent.data || []).map(r => (
                <tr
                  key={r.id}
                  className="border-t border-line bg-[rgba(9,14,32,0.4)] transition hover:bg-[rgba(15,22,45,0.7)]"
                  data-testid={`email-row-${r.id}`}
                >
                  <td className="px-3 py-2 font-mono text-[11px] text-fg-3">{new Date(r.created_at).toLocaleString()}</td>
                  <td className="px-3 py-2 font-mono text-[11px] uppercase tracking-[0.15em] text-cyan-signal">{r.template}</td>
                  <td className="px-3 py-2 text-fg">{r.recipient}</td>
                  <td className="px-3 py-2 max-w-[26vw] truncate text-fg-2">{r.subject}</td>
                  <td className="px-3 py-2">
                    <span className={STATUS_CHIP[r.status] || 'chip'}>
                      {STATUS_ICON[r.status]} {r.status}
                    </span>
                  </td>
                </tr>
              ))}
              {(recent.data || []).length === 0 && !recent.isLoading && (
                <tr><td colSpan={5} className="px-3 py-8 text-center text-sm text-fg-3">No emails sent yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Quick-links strip */}
      <div className="grid gap-3 md:grid-cols-3">
        <a
          href="https://resend.com/api-keys"
          target="_blank"
          rel="noreferrer"
          className="ghost-button flex items-center justify-between rounded-xl px-4 py-3 text-sm"
          data-testid="link-resend-keys"
        >
          <span>Get / rotate API key</span>
          <ArrowUpRight className="h-4 w-4" />
        </a>
        <a
          href="https://resend.com/domains"
          target="_blank"
          rel="noreferrer"
          className="ghost-button flex items-center justify-between rounded-xl px-4 py-3 text-sm"
          data-testid="link-resend-domains"
        >
          <span>Verify sender domain</span>
          <ArrowUpRight className="h-4 w-4" />
        </a>
        <a
          href="https://resend.com/webhooks"
          target="_blank"
          rel="noreferrer"
          className="ghost-button flex items-center justify-between rounded-xl px-4 py-3 text-sm"
          data-testid="link-resend-webhooks"
        >
          <span>Configure webhook</span>
          <ArrowUpRight className="h-4 w-4" />
        </a>
      </div>
    </div>
  );
}
