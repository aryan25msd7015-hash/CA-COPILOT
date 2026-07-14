'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Client } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import StatusBadge from '@/components/shared/StatusBadge';
import PaymentsTab from '@/components/billing/PaymentsTab';
import EmailSignalsTab from '@/components/email/EmailSignalsTab';

interface BillingOverview {
  invoice_count: number;
  outstanding: number;
  overdue: number;
  collected: number;
  collection_rate: number;
  active_plans: number;
  plans_due_next_30: number;
  by_status: Record<string, number>;
  ageing: Record<string, number>;
}

interface Invoice {
  id: string;
  client_id: string;
  client_name: string;
  invoice_no: string;
  issue_date: string;
  due_date: string;
  total: number;
  amount_paid: number;
  outstanding: number;
  days_overdue: number;
  status: string;
  payment_link?: string;
}

interface BillingPlan {
  id: string;
  client_id: string;
  client_name: string;
  name: string;
  service_scope: string[];
  frequency: string;
  amount: number;
  tax_rate: number;
  next_invoice_date?: string;
  active: boolean;
}

interface PaymentReceipt {
  id: string;
  invoice_no: string;
  client_name: string;
  paid_at: string;
  amount: number;
  mode: string;
  reference?: string;
}

interface PlanUsage {
  plan: string;
  limits: Record<string, number | null>;
  usage: Record<string, number>;
  status: Record<string, string>;
}

const today = new Date().toISOString().slice(0, 10);

function money(value: number) {
  return `INR ${Number(value || 0).toLocaleString('en-IN')}`;
}

export default function BillingPage() {
  const [tab, setTab] = useState<'operations' | 'payments' | 'email'>('operations');
  const [invoiceFilters, setInvoiceFilters] = useState({ status: 'draft,sent,part_paid,overdue', client_id: '', due_to: '' });
  const [planClientId, setPlanClientId] = useState('');
  const [paymentClientId, setPaymentClientId] = useState('');
  const [selectedInvoiceId, setSelectedInvoiceId] = useState('');
  const [paymentAmount, setPaymentAmount] = useState('');
  const [gatewayMessage, setGatewayMessage] = useState('');
  const [form, setForm] = useState({
    client_id: '',
    description: 'Monthly professional fees',
    amount: '25000',
    issue_date: today,
    due_date: today,
  });
  const [planForm, setPlanForm] = useState({
    client_id: '',
    name: 'Monthly retainer',
    service_scope: 'GST, TDS, advisory',
    frequency: 'monthly',
    amount: '25000',
    tax_rate: '18',
    next_invoice_date: today,
  });

  const overview = useQuery<BillingOverview>({ queryKey: ['billing-overview'], queryFn: () => api.get('/billing/overview').then(r => r.data) });
  const planUsage = useQuery<PlanUsage>({ queryKey: ['billing-plan-usage'], queryFn: () => api.get('/billing/plan-usage').then(r => r.data) });
  const invoices = useQuery<Invoice[]>({
    queryKey: ['billing-invoices', invoiceFilters],
    queryFn: () => api.get('/billing/invoices', {
      params: {
        status: invoiceFilters.status || undefined,
        client_id: invoiceFilters.client_id || undefined,
        due_to: invoiceFilters.due_to || undefined,
      },
    }).then(r => r.data),
  });
  const plans = useQuery<BillingPlan[]>({
    queryKey: ['billing-plans', planClientId],
    queryFn: () => api.get('/billing/plans', { params: { client_id: planClientId || undefined } }).then(r => r.data),
  });
  const payments = useQuery<PaymentReceipt[]>({
    queryKey: ['billing-payments', paymentClientId],
    queryFn: () => api.get('/billing/payments', { params: { client_id: paymentClientId || undefined, limit: 100 } }).then(r => r.data),
  });
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });

  async function refreshBilling() {
    await Promise.all([overview.refetch(), planUsage.refetch(), invoices.refetch(), plans.refetch(), payments.refetch()]);
  }

  async function createInvoice(event: FormEvent) {
    event.preventDefault();
    const response = await api.post('/billing/invoices', {
      client_id: form.client_id,
      issue_date: form.issue_date,
      due_date: form.due_date,
      line_items: [{ description: form.description, amount: Number(form.amount) }],
      tax_rate: 18,
      status: 'sent',
    });
    setSelectedInvoiceId(response.data.id);
    setPaymentAmount(String(response.data.outstanding || ''));
    await refreshBilling();
  }

  async function createPlan(event: FormEvent) {
    event.preventDefault();
    await api.post('/billing/plans', {
      client_id: planForm.client_id,
      name: planForm.name,
      service_scope: planForm.service_scope.split(',').map(item => item.trim()).filter(Boolean),
      frequency: planForm.frequency,
      amount: Number(planForm.amount),
      tax_rate: Number(planForm.tax_rate),
      next_invoice_date: planForm.next_invoice_date,
      active: true,
    });
    await refreshBilling();
  }

  async function recordPayment(event: FormEvent) {
    event.preventDefault();
    if (!selectedInvoiceId || !paymentAmount) return;
    await api.post(`/billing/invoices/${selectedInvoiceId}/payments`, {
      amount: Number(paymentAmount),
      paid_at: today,
      mode: 'bank_transfer',
      reference: 'Manual receipt',
    });
    setPaymentAmount('');
    await refreshBilling();
  }

  async function markInvoice(invoice: Invoice, status: string) {
    await api.patch(`/billing/invoices/${invoice.id}`, { status });
    await refreshBilling();
  }

  async function generatePaymentLink(invoice: Invoice) {
    setGatewayMessage('');
    try {
      const response = await api.post(`/billing/invoices/${invoice.id}/payment-link`);
      const link = response.data?.invoice?.payment_link;
      setGatewayMessage(link ? `Payment link generated for ${invoice.invoice_no}` : `Gateway request completed for ${invoice.invoice_no}`);
      await refreshBilling();
    } catch (err: unknown) {
      const detail = typeof err === 'object' && err && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setGatewayMessage(detail || 'Could not generate payment link');
    }
  }

  const selectedInvoice = (invoices.data || []).find(item => item.id === selectedInvoiceId);
  const metrics = [
    ['Outstanding', money(overview.data?.outstanding || 0)],
    ['Overdue', money(overview.data?.overdue || 0)],
    ['Collected', money(overview.data?.collected || 0)],
    ['Collection rate', `${overview.data?.collection_rate || 0}%`],
    ['Active plans', overview.data?.active_plans || 0],
    ['Plans due 30d', overview.data?.plans_due_next_30 || 0],
  ];

  return (
    <div className="space-y-5" data-testid="billing-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
            REVENUE OPS · SECTOR 06
          </p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-fg-0">Billing & Collections</h1>
          <p className="mt-1 max-w-2xl text-sm text-fg-2">
            Fee plans, invoices, payment tracking, ageing, and Razorpay-powered collections.
          </p>
        </div>
        <div className="inline-flex rounded-xl border border-line bg-[rgba(9,14,32,0.55)] p-1" data-testid="billing-tabs">
          {(['operations', 'payments', 'email'] as const).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              data-testid={`billing-tab-${t}`}
              className={`rounded-lg px-4 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.2em] transition ${
                tab === t
                  ? 'bg-gradient-to-r from-cyan-500/25 to-violet-500/15 text-fg-0 shadow-[inset_0_0_0_1px_rgba(34,211,238,0.45)]'
                  : 'text-fg-2 hover:text-fg'
              }`}
            >
              {t === 'operations' ? 'Operations' : t === 'payments' ? 'Payments · Razorpay' : 'Email · Resend'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'payments' && <PaymentsTab invoices={invoices.data || []} />}
      {tab === 'email' && <EmailSignalsTab />}
      {tab === 'operations' && (
        <>
      <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-6">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-lg font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Plan usage</h2>
            <p className="mt-1 text-xs text-slate-500">Current commercial limits and tenant consumption.</p>
          </div>
          <StatusBadge value={planUsage.data?.plan || 'plan'} />
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-5">
          {Object.entries(planUsage.data?.usage || {}).map(([key, used]) => {
            const limit = planUsage.data?.limits?.[key];
            const status = planUsage.data?.status?.[key] || 'ok';
            return (
              <div key={key} className="rounded-lg bg-slate-50 p-3">
                <p className="text-xs capitalize text-slate-500">{key.replaceAll('_', ' ')}</p>
                <p className="mt-1 text-sm font-semibold text-slate-950">{used} / {limit ?? 'unlimited'}</p>
                <p className={`mt-1 text-xs font-medium ${status === 'exceeded' ? 'text-rose-600' : status === 'near_limit' ? 'text-amber-600' : 'text-emerald-600'}`}>{status.replace('_', ' ')}</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-900">Ageing</h2>
        <div className="mt-3 grid gap-3 md:grid-cols-5">
          {Object.entries(overview.data?.ageing || {}).map(([bucket, value]) => (
            <div key={bucket} className="rounded-lg bg-slate-50 p-3">
              <p className="text-xs text-slate-500">{bucket.replace('_', '-')} days</p>
              <p className="mt-1 text-sm font-semibold text-slate-950">{money(value)}</p>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Invoice register</h2>
              <p className="mt-1 text-xs text-slate-500">Filter active receivables and record collections.</p>
            </div>
            <StatusBadge value={`${invoices.data?.length || 0} invoices`} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <select value={invoiceFilters.status} onChange={e => setInvoiceFilters({ ...invoiceFilters, status: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="draft,sent,part_paid,overdue">Open receivables</option>
              <option value="sent">Sent</option>
              <option value="part_paid">Part paid</option>
              <option value="paid">Paid</option>
              <option value="">All</option>
            </select>
            <ClientSelect clients={clients.data || []} value={invoiceFilters.client_id} onChange={value => setInvoiceFilters({ ...invoiceFilters, client_id: value })} />
            <input type="date" value={invoiceFilters.due_to} onChange={e => setInvoiceFilters({ ...invoiceFilters, due_to: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" />
          </div>
          {gatewayMessage && <p className="mt-3 rounded-lg bg-sky-50 px-3 py-2 text-xs font-medium text-sky-700">{gatewayMessage}</p>}
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Invoice</th>
                  <th className="px-4 py-3">Client</th>
                  <th className="px-4 py-3">Due</th>
                  <th className="px-4 py-3">Total</th>
                  <th className="px-4 py-3">Outstanding</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(invoices.data || []).map(invoice => (
                  <tr key={invoice.id} className="border-t border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">{invoice.invoice_no}</td>
                    <td className="px-4 py-3 text-slate-600">{invoice.client_name}</td>
                    <td className="px-4 py-3 text-slate-600">{invoice.due_date}{invoice.days_overdue > 0 ? ` (${invoice.days_overdue}d late)` : ''}</td>
                    <td className="px-4 py-3 text-slate-600">{money(invoice.total)}</td>
                    <td className="px-4 py-3 text-slate-600">{money(invoice.outstanding)}</td>
                    <td className="px-4 py-3"><StatusBadge value={invoice.status} /></td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex justify-end gap-2">
                        {invoice.payment_link && (
                          <a href={invoice.payment_link} target="_blank" rel="noreferrer" className="rounded-md border border-sky-200 px-2 py-1 text-xs text-sky-700">
                            Pay link
                          </a>
                        )}
                        {invoice.outstanding > 0 && !invoice.payment_link && (
                          <button onClick={() => generatePaymentLink(invoice)} className="rounded-md border border-sky-200 px-2 py-1 text-xs text-sky-700">
                            Checkout
                          </button>
                        )}
                        {invoice.outstanding > 0 && <button onClick={() => { setSelectedInvoiceId(invoice.id); setPaymentAmount(String(invoice.outstanding)); }} className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700">Receipt</button>}
                        {invoice.status !== 'void' && <button onClick={() => markInvoice(invoice, 'void')} className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700">Void</button>}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="space-y-4">
          <form onSubmit={createInvoice} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Create invoice</h2>
            <div className="mt-3 space-y-3">
              <ClientSelect clients={clients.data || []} value={form.client_id} onChange={value => setForm({ ...form, client_id: value })} />
              <input required value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <input required type="number" value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <div className="grid grid-cols-2 gap-2">
                <input type="date" value={form.issue_date} onChange={e => setForm({ ...form, issue_date: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
                <input type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
              </div>
              <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Create invoice</button>
            </div>
          </form>

          <form onSubmit={recordPayment} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Record payment</h2>
            <div className="mt-3 space-y-3">
              <select value={selectedInvoiceId} onChange={e => setSelectedInvoiceId(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
                <option value="">Select invoice</option>
                {(invoices.data || []).filter(invoice => invoice.outstanding > 0).map(invoice => <option key={invoice.id} value={invoice.id}>{invoice.invoice_no} / {invoice.client_name}</option>)}
              </select>
              <input required type="number" value={paymentAmount} onChange={e => setPaymentAmount(e.target.value)} placeholder={selectedInvoice ? String(selectedInvoice.outstanding) : 'Amount'} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <button className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700">Post receipt</button>
            </div>
          </form>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Billing plans</h2>
              <p className="mt-1 text-xs text-slate-500">Retainers and recurring fee plans.</p>
            </div>
            <ClientSelect clients={clients.data || []} value={planClientId} onChange={setPlanClientId} />
          </div>
          <form onSubmit={createPlan} className="mt-3 grid gap-2 md:grid-cols-3">
            <ClientSelect clients={clients.data || []} value={planForm.client_id} onChange={value => setPlanForm({ ...planForm, client_id: value })} />
            <input value={planForm.name} onChange={e => setPlanForm({ ...planForm, name: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input type="number" value={planForm.amount} onChange={e => setPlanForm({ ...planForm, amount: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <input value={planForm.service_scope} onChange={e => setPlanForm({ ...planForm, service_scope: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm md:col-span-2" />
            <button className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Create plan</button>
          </form>
          <div className="mt-4 space-y-2">
            {(plans.data || []).map(plan => (
              <div key={plan.id} className="rounded-md border border-slate-200 px-3 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">{plan.name} / {plan.client_name}</p>
                  <StatusBadge value={plan.active ? 'active' : 'inactive'} />
                </div>
                <p className="mt-1 text-xs text-slate-500">{plan.frequency} / {money(plan.amount)} + {plan.tax_rate}% tax / Next {plan.next_invoice_date || '-'}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Payment receipts</h2>
              <p className="mt-1 text-xs text-slate-500">Latest collections posted against invoices.</p>
            </div>
            <ClientSelect clients={clients.data || []} value={paymentClientId} onChange={setPaymentClientId} />
          </div>
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-2">Date</th>
                  <th className="px-3 py-2">Invoice</th>
                  <th className="px-3 py-2">Client</th>
                  <th className="px-3 py-2">Amount</th>
                </tr>
              </thead>
              <tbody>
                {(payments.data || []).map(payment => (
                  <tr key={payment.id} className="border-t border-slate-100">
                    <td className="px-3 py-2">{payment.paid_at}</td>
                    <td className="px-3 py-2">{payment.invoice_no}</td>
                    <td className="px-3 py-2">{payment.client_name}</td>
                    <td className="px-3 py-2">{money(payment.amount)}</td>
                  </tr>
                ))}
                {!payments.data?.length && <tr className="border-t"><td colSpan={4} className="px-3 py-8 text-center text-sm text-slate-500">No receipts found.</td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      </div>
        </>
      )}
    </div>
  );
}
