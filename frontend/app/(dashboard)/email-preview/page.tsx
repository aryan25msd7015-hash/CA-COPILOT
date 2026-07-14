'use client';

import { useEffect, useState, useMemo } from 'react';

const SAMPLE_PROPS: Record<string, any> = {
  password_reset: {
    user_name: 'Priya',
    reset_url: 'https://cacopilot.example.com/reset?token=demo',
    expires_in: '30 minutes',
  },
  email_verification: {
    user_name: 'Priya',
    verify_url: 'https://cacopilot.example.com/verify?token=demo',
    workspace_name: 'Nova & Partners LLP',
  },
  user_invitation: {
    invitee_name: 'Arjun',
    inviter_name: 'Priya \u00b7 Partner',
    workspace_name: 'Nova & Partners LLP',
    role: 'Manager',
    accept_url: 'https://cacopilot.example.com/invite?token=demo',
  },
  invoice_sent: {
    client_name: 'Aurora Textiles Pvt Ltd',
    invoice_no: 'INV-2026-1042',
    amount_inr: 148500,
    due_date: '15 Aug 2026',
    view_url: 'https://cacopilot.example.com/portal/invoices/inv-1042',
    pay_url: 'https://rzp.io/l/inv-1042',
  },
  payment_received: {
    client_name: 'Aurora Textiles Pvt Ltd',
    invoice_no: 'INV-2026-1042',
    amount_inr: 148500,
    paid_at: '14 Jul 2026 \u00b7 16:42 IST',
    method: 'Razorpay \u00b7 UPI',
    receipt_url: 'https://cacopilot.example.com/receipts/inv-1042.pdf',
  },
  invoice_overdue: {
    client_name: 'Meridian Systems LLP',
    invoice_no: 'INV-2026-0921',
    amount_inr: 84200,
    days_overdue: 12,
    pay_url: 'https://rzp.io/l/inv-0921',
  },
  subscription_activated: {
    workspace_name: 'Nova & Partners LLP',
    plan_name: 'Pro',
    amount_inr: 5999,
    next_charge_at: '14 Aug 2026',
    dashboard_url: 'https://cacopilot.example.com/dashboard',
  },
  subscription_cancelled: {
    workspace_name: 'Nova & Partners LLP',
    plan_name: 'Pro',
    ends_at: '31 Aug 2026',
    reactivate_url: 'https://cacopilot.example.com/billing/reactivate',
  },
  subscription_halted: {
    workspace_name: 'Nova & Partners LLP',
    plan_name: 'Pro',
    reason: 'card_declined',
    update_payment_url: 'https://cacopilot.example.com/billing/payment-method',
  },
  document_request: {
    client_name: 'Aurora Textiles Pvt Ltd',
    ca_name: 'Priya \u00b7 Nova & Partners',
    document_list: [
      'Bank statement \u00b7 SBI \u00b7 Q1 FY26',
      'GSTR-2B \u00b7 June 2026',
      'Purchase register \u00b7 June 2026',
    ],
    due_date: '20 Jul 2026',
    upload_url: 'https://cacopilot.example.com/portal/upload/req-42',
  },
  report_ready: {
    client_name: 'Aurora Textiles Pvt Ltd',
    report_name: 'GST Reconciliation',
    period: 'Jun 2026',
    headline_metric: { label: 'Mismatched ITC', value: '\u20B914,200', tone: 'warn' },
    view_url: 'https://cacopilot.example.com/portal/reports/rec-jun26',
  },
  portal_invite: {
    contact_name: 'Anil (Finance, Aurora Textiles)',
    ca_firm_name: 'Nova & Partners LLP',
    portal_url: 'https://cacopilot.example.com/portal/enter?token=demo',
  },
};

export default function EmailPreviewPage() {
  const [templates, setTemplates] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>('email_verification');
  const [html, setHtml] = useState<string>('');
  const [subject, setSubject] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/emails-render')
      .then((r) => r.json())
      .then((d) => setTemplates(d.templates || []))
      .catch(() => setTemplates([]));
  }, []);

  const props = useMemo(() => SAMPLE_PROPS[selected] || {}, [selected]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch('/emails-render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: selected, props }),
    })
      .then(async (r) => {
        const d = await r.json();
        if (cancelled) return;
        if (!r.ok) {
          setError(d?.error || `HTTP ${r.status}`);
          setHtml('');
          setSubject('');
        } else {
          setHtml(d.html);
          setSubject(d.subject);
        }
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [selected, props]);

  return (
    <div className="min-h-screen bg-[#050810] text-slate-200">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6">
          <div className="font-mono text-xs uppercase tracking-widest text-cyan-400">
            EMAIL · PREVIEW STUDIO
          </div>
          <h1 className="mt-1 text-2xl font-semibold text-slate-100">
            HUD-branded transactional templates
          </h1>
          <p className="mt-2 text-sm text-slate-400">
            Live render of every React Email template with sample props. The exact HTML shipped here is what Resend delivers.
          </p>
        </div>

        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-3">
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <div className="px-2 pb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
                Templates · {templates.length}
              </div>
              <ul className="space-y-1">
                {templates.map((t) => (
                  <li key={t}>
                    <button
                      onClick={() => setSelected(t)}
                      className={`w-full rounded-lg px-3 py-2 text-left text-sm font-mono transition ${
                        selected === t
                          ? 'bg-cyan-500/10 text-cyan-300 ring-1 ring-cyan-500/40'
                          : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
                      }`}
                      data-testid={`btn-template-${t}`}
                    >
                      {t}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </aside>

          <main className="col-span-9">
            <div className="mb-3 flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3">
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-slate-500">Subject</div>
                <div className="font-mono text-sm text-slate-100" data-testid="preview-subject">
                  {subject || (loading ? 'Rendering…' : '—')}
                </div>
              </div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
                {loading ? 'RENDERING' : error ? 'ERROR' : 'READY'}
              </div>
            </div>

            {error && (
              <div className="mb-3 rounded-xl border border-rose-800 bg-rose-950/40 px-4 py-3 font-mono text-xs text-rose-300">
                {error}
              </div>
            )}

            <div className="overflow-hidden rounded-xl border border-slate-800 bg-white">
              <iframe
                title="Email preview"
                srcDoc={html}
                className="h-[820px] w-full"
                data-testid="preview-iframe"
              />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
