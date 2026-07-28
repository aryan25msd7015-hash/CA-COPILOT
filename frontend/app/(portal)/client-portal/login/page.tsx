'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';
import axios from 'axios';
import { confirmPortalMagicLink, requestPortalMagicLink, setPortalSession } from '@/lib/portalAuth';
import { DEMO_ACCOUNTS } from '@/lib/demoAccounts';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const CLIENT_DEMO = DEMO_ACCOUNTS.find(item => item.tier === 'client')!;

export default function ClientPortalLoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState(CLIENT_DEMO.email);
  const [token, setToken] = useState('');
  const [devToken, setDevToken] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  async function useDemoClient() {
    setLoading(true);
    setMessage('');
    try {
      const { data } = await axios.post(`${API_BASE}/client-portal/auth/demo-login`, { email: CLIENT_DEMO.email });
      setPortalSession(data.access_token, { contact: data.contact, client: data.client });
      router.push('/client-portal');
    } catch (err: unknown) {
      try {
        const link = await requestPortalMagicLink(CLIENT_DEMO.email);
        if (link.token) {
          setDevToken(link.token);
          setToken(link.token);
          setMessage('Demo contact found. Confirm the token below.');
        } else {
          setMessage(err instanceof Error ? err.message : 'Demo portal login failed. Seed demo data first.');
        }
      } catch (inner: unknown) {
        setMessage(inner instanceof Error ? inner.message : 'Demo portal login failed');
      }
    } finally {
      setLoading(false);
    }
  }

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
    <div className="mx-auto flex min-h-screen max-w-lg flex-col justify-center bg-stone-100 px-4 py-10 text-stone-900">
      <div className="rounded-2xl border border-stone-300 bg-white p-8 shadow-sm">
        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-teal-800">Client portal</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-stone-950">CA · COPILOT</h1>
        <p className="mt-2 text-sm text-stone-600">
          Separate login for clients — firm modules stay on the other side of the wall.
        </p>

        <button
          type="button"
          onClick={useDemoClient}
          disabled={loading}
          className="mt-6 w-full rounded-lg border border-teal-700 bg-teal-50 px-3 py-2 text-sm font-medium text-teal-950 disabled:opacity-50"
        >
          Use client demo ({CLIENT_DEMO.email})
        </button>

        <form onSubmit={requestLink} className="mt-8 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@company.com"
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-950"
          />
          <button disabled={loading} className="w-full rounded-lg bg-stone-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">
            Email magic link
          </button>
        </form>

        <form onSubmit={confirm} className="mt-6 space-y-3 border-t border-stone-200 pt-6">
          <p className="text-xs text-stone-500">Paste the one-time portal token to continue</p>
          <input
            value={token}
            onChange={e => setToken(e.target.value)}
            placeholder="Portal token"
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm text-stone-950"
          />
          <button disabled={loading || !token} className="w-full rounded-lg border border-stone-400 px-3 py-2 text-sm text-stone-900 disabled:opacity-50">
            Enter portal
          </button>
        </form>

        {devToken && (
          <p className="mt-4 break-all rounded-lg bg-stone-50 p-3 text-[11px] text-stone-700">
            Dev token: {devToken}
          </p>
        )}
        {message && <p className="mt-4 text-xs text-stone-600">{message}</p>}
      </div>
    </div>
  );
}
