'use client';

import { useState } from 'react';
import { ArrowLeft, MailCheck } from 'lucide-react';
import { api } from '@/lib/api';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const response = await api.post('/auth/password-reset/request', { email });
      const tokenHint = response.data?.token ? ` Development token: ${response.data.token}` : '';
      setMessage(`If that email exists, a reset link has been sent.${tokenHint}`);
    } catch (err: unknown) {
      const detail = typeof err === 'object' && err && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Could not request a reset link');
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f7fb] px-4 py-10">
      <section className="w-full max-w-md rounded-[28px] border border-white/70 bg-white/90 p-7 shadow-[0_30px_90px_rgba(15,23,42,0.16)] backdrop-blur">
        <a href="/login" className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900">
          <ArrowLeft className="h-4 w-4" />
          Back to sign in
        </a>
        <div className="mt-6 grid h-12 w-12 place-items-center rounded-2xl bg-sky-50 text-sky-600">
          <MailCheck className="h-6 w-6" />
        </div>
        <h1 className="mt-4 text-2xl font-semibold text-slate-950">Reset password</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Enter your account email and CA Copilot will send a secure reset link.
        </p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50/80 px-3 text-sm outline-none transition focus:border-sky-400 focus:bg-white focus:ring-4 focus:ring-sky-500/10"
              placeholder="you@firm.com"
            />
          </div>
          {message && <p className="rounded-2xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p>}
          {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="liquid-button h-11 w-full rounded-2xl text-sm font-medium text-white outline-none transition focus-visible:ring-4 focus-visible:ring-sky-500/20 disabled:opacity-50"
          >
            {loading ? 'Sending...' : 'Send reset link'}
          </button>
        </form>
      </section>
    </main>
  );
}
