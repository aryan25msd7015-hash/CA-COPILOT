/**
 * Razorpay Checkout client helper.
 *
 * Flow:
 *   1. `openCheckout()` calls the backend to create a Razorpay Order (or uses
 *      one already created).
 *   2. Loads the Razorpay Checkout script on-demand if not already present.
 *   3. Opens the hosted Checkout modal.
 *   4. On success, POSTs back to `/razorpay/verify-payment` so the server can
 *      HMAC-verify the signature and reconcile the invoice.
 *
 * The KEY_ID is fetched from `/razorpay/config` (never hard-coded on the
 * client; the secret NEVER leaves the backend).
 */
import { api } from '@/lib/api';

interface Window {
  Razorpay: unknown;
}

const CHECKOUT_SCRIPT = 'https://checkout.razorpay.com/v1/checkout.js';

let scriptLoading: Promise<void> | null = null;

function loadCheckoutScript(): Promise<void> {
  if (typeof window === 'undefined') return Promise.reject(new Error('SSR context'));
  if ((window as unknown as { Razorpay?: unknown }).Razorpay) return Promise.resolve();
  if (scriptLoading) return scriptLoading;
  scriptLoading = new Promise((resolve, reject) => {
    const el = document.createElement('script');
    el.src = CHECKOUT_SCRIPT;
    el.async = true;
    el.onload = () => resolve();
    el.onerror = () => {
      scriptLoading = null;
      reject(new Error('Failed to load Razorpay Checkout script'));
    };
    document.head.appendChild(el);
  });
  return scriptLoading;
}

export interface OpenCheckoutArgs {
  amount_inr: number;
  receipt: string;
  description?: string;
  invoice_id?: string;
  client_id?: string;
  prefill?: { name?: string; email?: string; contact?: string };
  theme_color?: string;
}

export interface CheckoutResult {
  status: 'success' | 'dismissed' | 'error';
  razorpay_payment_id?: string;
  razorpay_order_id?: string;
  razorpay_signature?: string;
  error?: string;
}

interface RazorpayCtor {
  new (options: Record<string, unknown>): { open(): void; on(event: string, cb: (r: unknown) => void): void };
}

export async function openCheckout(args: OpenCheckoutArgs): Promise<CheckoutResult> {
  const { data: order } = await api.post('/razorpay/orders', {
    amount_inr: args.amount_inr,
    receipt: args.receipt.slice(0, 40),
    invoice_id: args.invoice_id,
    client_id: args.client_id,
    description: args.description,
  });

  await loadCheckoutScript();

  return new Promise<CheckoutResult>((resolve) => {
    const RZ = (window as unknown as { Razorpay: RazorpayCtor }).Razorpay;
    const options: Record<string, unknown> = {
      key: order.key_id,
      amount: order.amount_paise,
      currency: order.currency || 'INR',
      order_id: order.order_id,
      name: 'CA Copilot',
      description: args.description || `Payment · ${args.receipt}`,
      image: undefined,
      prefill: args.prefill || {},
      notes: order.notes || {},
      theme: { color: args.theme_color || '#22d3ee' },
      handler: async (resp: {
        razorpay_payment_id: string;
        razorpay_order_id: string;
        razorpay_signature: string;
      }) => {
        try {
          await api.post('/razorpay/verify-payment', {
            razorpay_order_id: resp.razorpay_order_id,
            razorpay_payment_id: resp.razorpay_payment_id,
            razorpay_signature: resp.razorpay_signature,
            invoice_id: args.invoice_id,
          });
          resolve({ status: 'success', ...resp });
        } catch (e: unknown) {
          resolve({
            status: 'error',
            error: e instanceof Error ? e.message : 'Verification failed',
            ...resp,
          });
        }
      },
      modal: {
        ondismiss: () => resolve({ status: 'dismissed' }),
      },
    };
    const inst = new RZ(options);
    inst.on('payment.failed', (r: unknown) => {
      const err = (r as { error?: { description?: string } })?.error?.description || 'Payment failed';
      resolve({ status: 'error', error: err });
    });
    inst.open();
  });
}

export async function fetchRazorpayConfig() {
  const { data } = await api.get('/razorpay/config');
  return data as {
    key_id: string;
    configured: boolean;
    webhook_configured: boolean;
    currency: string;
    test_mode: boolean;
    preview_stub?: boolean;
  };
}

export async function fetchPlans() {
  const { data } = await api.get('/razorpay/plans');
  return data as Array<{
    code: string;
    name: string;
    tagline: string;
    amount_inr: number;
    period: string;
    interval: number;
    features: string[];
  }>;
}

export async function startSubscription(plan_code: string, total_count = 12) {
  const { data } = await api.post('/razorpay/subscriptions', { plan_code, total_count });
  return data as {
    id: string;
    razorpay_subscription_id: string;
    short_url: string | null;
    status: string;
    plan_code: string;
  };
}

export async function cancelSubscription(id: string) {
  const { data } = await api.delete(`/razorpay/subscriptions/${id}`);
  return data;
}

export async function createStandalonePaymentLink(payload: {
  amount_inr: number;
  description: string;
  customer_name: string;
  customer_email?: string;
  customer_contact?: string;
  expire_in_days?: number;
}) {
  const { data } = await api.post('/razorpay/payment-links', payload);
  return data as { id: string; short_url: string; amount_inr: number; status: string };
}
