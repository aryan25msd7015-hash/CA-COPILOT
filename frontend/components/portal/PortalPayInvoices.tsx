'use client';

import { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { CreditCard, Loader2, Radio, ShieldCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { openCheckout } from '@/lib/razorpay';

interface OpenInvoice {
  id: string;
  invoice_no: string;
  client_id: string;
  client_name: string;
  total: number;
  outstanding: number;
  due_date: string;
  status: string;
}

function money(n: number) {
  return `₹${Number(n || 0).toLocaleString('en-IN')}`;
}

export default function PortalPayInvoices() {
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const invs = useQuery<OpenInvoice[]>({
    queryKey: ['portal-open-invoices'],
    queryFn: () => api.get('/portal/invoices').then(r => r.data).catch(() => []),
  });

  const list = (invs.data || []).slice(0, 4);

  async function pay(inv: OpenInvoice) {
    setBusy(inv.id);
    setMsg(null);
    const res = await openCheckout({
      amount_inr: inv.outstanding,
      receipt: `INV-${inv.invoice_no}`.slice(0, 40),
      description: `Invoice ${inv.invoice_no} · ${inv.client_name}`,
      invoice_id: inv.id,
      client_id: inv.client_id,
      prefill: { name: inv.client_name },
    }).catch((e: Error) => ({ status: 'error' as const, error: e.message }));
    setBusy(null);
    if (res.status === 'success') {
      setMsg(`Payment captured · ${res.razorpay_payment_id}`);
      qc.invalidateQueries({ queryKey: ['portal-open-invoices'] });
    } else if (res.status === 'error') {
      setMsg(`Error: ${res.error}`);
    }
  }

  if (invs.isLoading || list.length === 0) return null;

  return (
    <section
      className="hud-panel jarvis-panel overflow-hidden rounded-2xl p-5"
      data-testid="portal-pay-invoices"
    >
      <div className="relative mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl border border-cyan-400/50 bg-cyan-500/10">
            <ShieldCheck className="h-4 w-4 text-cyan-300" />
          </span>
          <div>
            <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
              PAY YOUR CA · SECURE COLLECTIONS
            </p>
            <h2 className="mt-1 font-display text-lg font-semibold text-fg">Open invoices — pay via Razorpay</h2>
            <p className="mt-0.5 text-xs text-fg-2">Cards · UPI · Netbanking · Wallets · EMI. Amounts settle instantly.</p>
          </div>
        </div>
        <span className="chip chip-cyan">
          <Radio className="motion-blink h-3 w-3" /> {list.length} open
        </span>
      </div>

      {msg && (
        <p className="mb-3 rounded-xl border border-cyan-400/30 bg-cyan-500/[0.06] px-3 py-2 font-mono text-xs text-cyan-200" data-testid="portal-pay-msg">
          {msg}
        </p>
      )}

      <div className="relative grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {list.map(inv => (
          <div
            key={inv.id}
            className="hud-corners relative overflow-hidden rounded-xl border border-line bg-[rgba(6,11,26,0.5)] p-4"
            data-testid={`portal-pay-inv-${inv.id}`}
          >
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">{inv.invoice_no}</p>
            <p className="mt-1 truncate text-sm font-semibold text-fg">{inv.client_name}</p>
            <div className="mt-2 flex items-end gap-2">
              <span className="font-mono-num font-display text-2xl font-semibold text-fg-0">{money(inv.outstanding)}</span>
              <span className="pb-1 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">
                due {inv.due_date}
              </span>
            </div>
            <button
              type="button"
              onClick={() => pay(inv)}
              disabled={busy === inv.id}
              data-testid={`portal-pay-btn-${inv.id}`}
              className="liquid-button mt-3 flex h-9 w-full items-center justify-center gap-2 rounded-lg text-sm outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:opacity-60"
            >
              {busy === inv.id ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span className="font-mono text-[11px] uppercase tracking-[0.2em]">Opening…</span>
                </>
              ) : (
                <>
                  <CreditCard className="h-4 w-4" /> Pay now
                </>
              )}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
