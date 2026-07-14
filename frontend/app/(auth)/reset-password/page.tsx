'use client';

import { Suspense, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, KeyRound } from 'lucide-react';
import { api } from '@/lib/api';

function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const [token, setToken] = useState(searchParams.get('token') || '');
  const [password, setPassword] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    setMessage('');
    try {
      await api.post('/auth/password-reset/confirm', { token, new_password: password });
      setMessage('Password reset complete. You can sign in with the new password.');
      setPassword('');
    } catch (err: unknown) {
      const detail = typeof err === 'object' && err && 'response' in err
        ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
        : undefined;
      setError(detail || 'Could not reset password');
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={submit} className="mt-6 space-y-4">
      <div>
        <label htmlFor="token" className="mb-1 block text-sm font-medium text-slate-700">
          Reset token
        </label>
        <input
          id="token"
          required
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50/80 px-3 text-sm outline-none transition focus:border-sky-400 focus:bg-white focus:ring-4 focus:ring-sky-500/10"
          placeholder="Paste reset token"
        />
      </div>
      <div>
        <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
          New password
        </label>
        <input
          id="password"
          type="password"
          required
          minLength={8}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50/80 px-3 text-sm outline-none transition focus:border-sky-400 focus:bg-white focus:ring-4 focus:ring-sky-500/10"
          placeholder="At least 8 characters"
        />
      </div>
      {message && <p className="rounded-2xl bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p>}
      {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
      <button
        type="submit"
        disabled={loading}
        className="liquid-button h-11 w-full rounded-2xl text-sm font-medium text-white outline-none transition focus-visible:ring-4 focus-visible:ring-sky-500/20 disabled:opacity-50"
      >
        {loading ? 'Resetting...' : 'Reset password'}
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f7fb] px-4 py-10">
      <section className="w-full max-w-md rounded-[28px] border border-white/70 bg-white/90 p-7 shadow-[0_30px_90px_rgba(15,23,42,0.16)] backdrop-blur">
        <a href="/login" className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900">
          <ArrowLeft className="h-4 w-4" />
          Back to sign in
        </a>
        <div className="mt-6 grid h-12 w-12 place-items-center rounded-2xl bg-sky-50 text-sky-600">
          <KeyRound className="h-6 w-6" />
        </div>
        <h1 className="mt-4 text-2xl font-semibold text-slate-950">Choose a new password</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Use the token from your reset email. Existing sessions are revoked after reset.
        </p>
        <Suspense fallback={null}>
          <ResetPasswordForm />
        </Suspense>
      </section>
    </main>
  );
}
