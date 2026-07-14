'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowUpRight, CheckCircle2, CircleDot, Copy, CreditCard, Link2, Loader2, Radio,
  Sparkles, XCircle, Zap,
} from 'lucide-react';
import {
  cancelSubscription,
  createStandalonePaymentLink,
  fetchPlans,
  fetchRazorpayConfig,
  openCheckout,
  startSubscription,
} from '@/lib/razorpay';
import { api } from '@/lib/api';

interface Plan {
  code: string;
  name: string;
  tagline: string;
  amount_inr: number;
  period: string;
  features: string[];
}

interface Sub {
  id: string;
  plan_code: string;
  amount_inr: number;
  currency: string;
  status: string;
  short_url: string | null;
  next_charge_at: string | null;
  created_at: string;
}

interface Invoice {
  id: string;
  invoice_no: string;
  client_id: string;
  client_name: string;
  outstanding: number;
  total: number;
  status: string;
}

function money(n: number) {
  return `₹${Number(n || 0).toLocaleString('en-IN')}`;
}

export default function PaymentsTab({ invoices = [] }: { invoices?: Invoice[] }) {
  const qc = useQueryClient();
  const [flash, setFlash] = useState<{ kind: 'ok' | 'err' | 'info'; msg: string } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [linkForm, setLinkForm] = useState({
    amount_inr: '5000',
    description: 'Advisory fees · Q4',
    customer_name: '',
    customer_email: '',
    customer_contact: '',
  });
  const [lastLink, setLastLink] = useState<string | null>(null);

  const config = useQuery({ queryKey: ['rz-config'], queryFn: fetchRazorpayConfig });
  const plans = useQuery({ queryKey: ['rz-plans'], queryFn: fetchPlans });
  const subs = useQuery<Sub[]>({
    queryKey: ['rz-subs'],
    queryFn: () => api.get('/razorpay/subscriptions').then(r => r.data),
  });

  const openInvoices = (invoices || []).filter(i => (i.outstanding || 0) > 0).slice(0, 6);
  const stubMode = config.data?.preview_stub || !config.data?.configured;

  async function payInvoice(inv: Invoice) {
    setBusyId(inv.id);
    setFlash(null);
    const receipt = `INV-${inv.invoice_no}`.slice(0, 40);
    const res = await openCheckout({
      amount_inr: inv.outstanding,
      receipt,
      description: `Invoice ${inv.invoice_no} · ${inv.client_name}`,
      invoice_id: inv.id,
      client_id: inv.client_id,
      prefill: { name: inv.client_name },
    }).catch((e: Error) => ({ status: 'error' as const, error: e.message }));
    setBusyId(null);
    if (res.status === 'success') {
      setFlash({ kind: 'ok', msg: `Payment captured · ${res.razorpay_payment_id}` });
      qc.invalidateQueries({ queryKey: ['billing-invoices'] });
      qc.invalidateQueries({ queryKey: ['billing-overview'] });
    } else if (res.status === 'error') {
      setFlash({ kind: 'err', msg: res.error || 'Payment error' });
    } else {
      setFlash({ kind: 'info', msg: 'Checkout dismissed' });
    }
  }

  async function subscribe(plan: Plan) {
    setBusyId(plan.code);
    setFlash(null);
    try {
      const res = await startSubscription(plan.code);
      setFlash({ kind: 'ok', msg: `Subscription started · ${res.razorpay_subscription_id}` });
      if (res.short_url) window.open(res.short_url, '_blank', 'noopener');
      subs.refetch();
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string }).response?.data?.detail
        || (e as Error).message
        || 'Subscription failed';
      setFlash({ kind: 'err', msg });
    } finally {
      setBusyId(null);
    }
  }

  async function cancelSub(sub: Sub) {
    setBusyId(sub.id);
    try {
      await cancelSubscription(sub.id);
      setFlash({ kind: 'ok', msg: 'Subscription cancel scheduled at cycle end' });
      subs.refetch();
    } catch (e: unknown) {
      setFlash({ kind: 'err', msg: (e as Error).message });
    } finally {
      setBusyId(null);
    }
  }

  async function createLink(e: React.FormEvent) {
    e.preventDefault();
    setBusyId('link');
    try {
      const res = await createStandalonePaymentLink({
        amount_inr: Number(linkForm.amount_inr),
        description: linkForm.description,
        customer_name: linkForm.customer_name || 'Customer',
        customer_email: linkForm.customer_email || undefined,
        customer_contact: linkForm.customer_contact || undefined,
      });
      setLastLink(res.short_url);
      setFlash({ kind: 'ok', msg: 'Payment link generated' });
    } catch (e: unknown) {
      setFlash({ kind: 'err', msg: (e as Error).message });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-5" data-testid="payments-tab">
      {/* GATEWAY HEALTH STRIP */}
      <div className="hud-panel hud-corners flex flex-wrap items-center justify-between gap-3 rounded-2xl p-4">
        <div className="flex items-center gap-3">
          <span className={`grid h-10 w-10 place-items-center rounded-xl border ${
            config.data?.configured
              ? 'border-emerald-400/50 bg-emerald-500/10'
              : 'border-amber-400/50 bg-amber-500/10'
          }`}>
            <Radio className={`h-4 w-4 motion-blink ${config.data?.configured ? 'text-emerald-300' : 'text-amber-300'}`} />
          </span>
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
              GATEWAY · RAZORPAY
            </p>
            <p className="mt-0.5 text-sm font-medium text-fg">
              {config.data?.configured
                ? (config.data.test_mode ? 'Test mode · connected' : 'Live mode · connected')
                : stubMode ? 'Preview stub · drop-in Razorpay keys to go live' : 'Not configured'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={`chip ${config.data?.configured ? 'chip-emerald' : 'chip-amber'}`}>
            {config.data?.configured ? 'Configured' : 'Placeholders'}
          </span>
          <span className={`chip ${config.data?.webhook_configured ? 'chip-cyan' : 'chip-amber'}`}>
            Webhooks {config.data?.webhook_configured ? 'ok' : 'pending'}
          </span>
          <span className="chip chip-violet">INR only</span>
        </div>
      </div>

      {flash && (
        <div
          className={`hud-panel motion-pop flex items-start gap-3 rounded-xl border-l-4 p-3 ${
            flash.kind === 'ok'
              ? 'border-l-emerald-400 text-emerald-200'
              : flash.kind === 'err'
              ? 'border-l-rose-400 text-rose-200'
              : 'border-l-cyan-400 text-cyan-200'
          }`}
          data-testid="payments-flash"
        >
          {flash.kind === 'ok' && <CheckCircle2 className="mt-0.5 h-4 w-4" />}
          {flash.kind === 'err' && <XCircle className="mt-0.5 h-4 w-4" />}
          {flash.kind === 'info' && <CircleDot className="mt-0.5 h-4 w-4" />}
          <span className="font-mono text-xs">{flash.msg}</span>
        </div>
      )}

      {/* OPEN INVOICES */}
      <section className="hud-panel rounded-2xl p-5" data-testid="pay-invoices-card">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
              COLLECTIONS · CHECKOUT
            </p>
            <h3 className="mt-1 font-display text-lg font-semibold text-fg">Open invoices — one-tap Razorpay Checkout</h3>
            <p className="mt-0.5 text-xs text-fg-2">Amounts settle in your Razorpay account. Server verifies signature before marking paid.</p>
          </div>
          <span className="chip">{openInvoices.length} open</span>
        </div>
        {openInvoices.length === 0 && (
          <div className="rounded-xl border border-line bg-[rgba(9,14,32,0.4)] p-6 text-center">
            <Sparkles className="mx-auto h-6 w-6 text-cyan-300" />
            <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-3">Nothing pending — you&apos;re all clear.</p>
          </div>
        )}
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {openInvoices.map(inv => (
            <div
              key={inv.id}
              className="hud-corners group relative overflow-hidden rounded-xl border border-line bg-[rgba(9,14,32,0.55)] p-4 transition hover:-translate-y-0.5 hover:border-cyan-400/40"
              data-testid={`pay-invoice-${inv.id}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">{inv.invoice_no}</p>
                  <p className="mt-1 text-sm font-semibold text-fg">{inv.client_name}</p>
                </div>
                <span className={`chip ${inv.status === 'overdue' ? 'chip-rose' : 'chip-amber'}`}>{inv.status}</span>
              </div>
              <div className="mt-3 flex items-end gap-2">
                <span className="font-mono-num font-display text-2xl font-semibold text-fg-0">{money(inv.outstanding)}</span>
                <span className="pb-1 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">/ {money(inv.total)}</span>
              </div>
              <button
                type="button"
                onClick={() => payInvoice(inv)}
                disabled={busyId === inv.id}
                data-testid={`pay-invoice-btn-${inv.id}`}
                className="liquid-button mt-3 flex h-9 w-full items-center justify-center gap-2 rounded-lg text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:opacity-60"
              >
                {busyId === inv.id ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /><span className="font-mono text-[11px] uppercase tracking-[0.2em]">Opening…</span></>
                ) : (
                  <><CreditCard className="h-4 w-4" /> Pay via Razorpay <ArrowUpRight className="h-4 w-4 opacity-80" /></>
                )}
              </button>
            </div>
          ))}
        </div>
      </section>

      {/* SUBSCRIPTIONS */}
      <section className="hud-panel rounded-2xl p-5" data-testid="pay-subscriptions-card">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-violet-signal">
              SAAS · SUBSCRIPTION
            </p>
            <h3 className="mt-1 font-display text-lg font-semibold text-fg">Subscribe to CA Copilot</h3>
            <p className="mt-0.5 text-xs text-fg-2">Monthly recurring billing via Razorpay Subscriptions. Cancel anytime at cycle end.</p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-3">
          {(plans.data || []).map((plan, i) => {
            const isPro = plan.code === 'pro';
            return (
              <div
                key={plan.code}
                className={`hud-corners relative overflow-hidden rounded-2xl border p-5 transition ${
                  isPro
                    ? 'border-cyan-400/60 bg-gradient-to-b from-cyan-500/12 to-transparent shadow-[0_0_38px_-14px_rgba(34,211,238,0.7)]'
                    : 'border-line bg-[rgba(9,14,32,0.55)] hover:border-cyan-400/40'
                }`}
                data-testid={`plan-card-${plan.code}`}
              >
                {isPro && <span className="motion-blink absolute right-4 top-4 chip chip-cyan">Most popular</span>}
                <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-fg-3">
                  {String(i + 1).padStart(2, '0')} · {plan.name}
                </p>
                <p className="mt-1 text-xs text-fg-2">{plan.tagline}</p>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="font-mono-num font-display text-4xl font-semibold text-fg-0">{money(plan.amount_inr)}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">/ {plan.period}</span>
                </div>
                <ul className="mt-4 space-y-1.5">
                  {plan.features.map(f => (
                    <li key={f} className="flex items-start gap-2 text-xs text-fg-2">
                      <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-300" />
                      <span>{f}</span>
                    </li>
                  ))}
                </ul>
                <button
                  type="button"
                  onClick={() => subscribe(plan as Plan)}
                  disabled={busyId === plan.code}
                  data-testid={`subscribe-btn-${plan.code}`}
                  className={`mt-5 flex h-10 w-full items-center justify-center gap-2 rounded-xl text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:opacity-60 ${
                    isPro ? 'liquid-button' : 'ghost-button'
                  }`}
                >
                  {busyId === plan.code ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <>
                      <Zap className="h-4 w-4" /> Start {plan.name}
                    </>
                  )}
                </button>
              </div>
            );
          })}
        </div>

        {/* Active subscriptions */}
        <div className="mt-5 space-y-2" data-testid="active-subs">
          {(subs.data || []).map(s => (
            <div key={s.id} className="flex items-center justify-between rounded-xl border border-line bg-[rgba(9,14,32,0.55)] p-3">
              <div>
                <p className="text-sm font-medium text-fg">
                  {s.plan_code[0].toUpperCase() + s.plan_code.slice(1)} · {money(s.amount_inr)} / month
                </p>
                <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">
                  <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${
                    s.status === 'active' ? 'bg-emerald-400 motion-blink' : s.status === 'cancelled' ? 'bg-rose-400' : 'bg-amber-400'
                  }`} />
                  {s.status} · next charge {s.next_charge_at ? new Date(s.next_charge_at).toLocaleDateString() : 'TBA'}
                </p>
              </div>
              <div className="flex gap-2">
                {s.short_url && (
                  <a href={s.short_url} target="_blank" rel="noreferrer" className="chip chip-cyan">
                    Authorize <ArrowUpRight className="h-3 w-3" />
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => cancelSub(s)}
                  disabled={busyId === s.id || s.status === 'cancelled'}
                  data-testid={`cancel-sub-${s.id}`}
                  className="ghost-button rounded-lg px-3 py-1.5 text-xs disabled:opacity-50"
                >
                  {s.status === 'cancelled' ? 'Cancelled' : 'Cancel'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* STANDALONE PAYMENT LINK */}
      <section className="hud-panel rounded-2xl p-5" data-testid="pay-link-card">
        <div className="mb-4">
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
            AD-HOC · SHARE A PAY LINK
          </p>
          <h3 className="mt-1 font-display text-lg font-semibold text-fg">Generate a Razorpay Payment Link</h3>
          <p className="mt-0.5 text-xs text-fg-2">Send via WhatsApp / email — no invoice row needed.</p>
        </div>
        <form onSubmit={createLink} className="grid gap-3 md:grid-cols-6">
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Amount (INR)</span>
            <input
              type="number" min={1} required
              value={linkForm.amount_inr}
              onChange={e => setLinkForm({ ...linkForm, amount_inr: e.target.value })}
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="link-amount"
            />
          </label>
          <label className="flex flex-col gap-1 md:col-span-4">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Description</span>
            <input
              required
              value={linkForm.description}
              onChange={e => setLinkForm({ ...linkForm, description: e.target.value })}
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="link-desc"
            />
          </label>
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Customer name</span>
            <input
              value={linkForm.customer_name}
              onChange={e => setLinkForm({ ...linkForm, customer_name: e.target.value })}
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="link-name"
            />
          </label>
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Email</span>
            <input
              type="email"
              value={linkForm.customer_email}
              onChange={e => setLinkForm({ ...linkForm, customer_email: e.target.value })}
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="link-email"
            />
          </label>
          <label className="flex flex-col gap-1 md:col-span-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">Contact</span>
            <input
              value={linkForm.customer_contact}
              onChange={e => setLinkForm({ ...linkForm, customer_contact: e.target.value })}
              className="h-10 rounded-lg border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
              data-testid="link-contact"
            />
          </label>
          <div className="md:col-span-6">
            <button
              type="submit"
              disabled={busyId === 'link'}
              data-testid="link-create-btn"
              className="liquid-button flex h-10 items-center gap-2 rounded-xl px-4 text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:opacity-60"
            >
              {busyId === 'link' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
              Generate link
            </button>
          </div>
        </form>
        {lastLink && (
          <div className="mt-4 flex items-center justify-between rounded-xl border border-cyan-400/30 bg-cyan-500/[0.06] p-3">
            <a href={lastLink} target="_blank" rel="noreferrer" className="truncate font-mono text-xs text-cyan-200" data-testid="link-result">
              {lastLink}
            </a>
            <button
              type="button"
              onClick={() => { navigator.clipboard.writeText(lastLink); setFlash({ kind: 'ok', msg: 'Copied to clipboard' }); }}
              className="ghost-button rounded-lg px-3 py-1.5 text-xs"
              data-testid="link-copy-btn"
            >
              <Copy className="mr-1 inline h-3 w-3" /> Copy
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
