'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import { confirmPortalMagicLink, requestPortalMagicLink } from '@/lib/portalAuth';

export default function ClientPortalLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [devToken, setDevToken] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function requestLink(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      const data = await requestPortalMagicLink(email);
      setMessage(data.detail);
      if (data.token) {
        setDevToken(data.token);
        setToken(data.token);
      }
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : 'Request failed');
    } finally {
      setLoading(false);
    }
  }

  async function confirm(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      await confirmPortalMagicLink(token);
      router.push('/client-portal');
    } catch (err: unknown) {
      setMessage(err instanceof Error ? err.message : 'Confirm failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center px-4 py-10">
      <div className="rounded-2xl border border-cyan-400/30 bg-[rgba(8,12,26,0.9)] p-8 shadow-[0_0_60px_rgba(34,211,238,0.15)]">
        <p className="font-mono text-[10px] uppercase tracking-[0.3em] text-cyan-300">Client portal</p>
        <h1 className="mt-2 font-display text-3xl font-semibold text-white">CA · COPILOT</h1>
        <p className="mt-2 text-sm text-slate-300">
          Separate login for clients — your firm data stays on the other side of the wall.
        </p>

        <form onSubmit={requestLink} className="mt-8 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white"
          />
          <button disabled={loading} className="w-full rounded-lg bg-cyan-500 px-3 py-2 text-sm font-medium text-slate-950 disabled:opacity-50">
            Email magic link
          </button>
        </form>

        <form onSubmit={confirm} className="mt-6 space-y-3 border-t border-white/10 pt-6">
          <p className="text-xs text-slate-400">Paste the one-time portal token to continue</p>
          <input
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="Portal token"
            className="w-full rounded-lg border border-white/15 bg-black/30 px-3 py-2 text-sm text-white"
          />
          <button disabled={loading || !token} className="w-full rounded-lg border border-cyan-400/40 px-3 py-2 text-sm text-cyan-100 disabled:opacity-50">
            Enter portal
          </button>
        </form>

        {devToken && (
          <p className="mt-4 break-all rounded-lg bg-emerald-500/10 p-3 text-xs text-emerald-200">
            Dev token: {devToken}
          </p>
        )}
        {message && <p className="mt-4 text-sm text-slate-300">{message}</p>}
      </div>
    </div>
  );
}
