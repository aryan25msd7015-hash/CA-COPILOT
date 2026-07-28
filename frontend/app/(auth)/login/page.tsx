'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { startGoogleSignIn } from '@/lib/googleAuth';
import { DEMO_ACCOUNTS, DemoAccount, homeForRole } from '@/lib/demoAccounts';
import { confirmPortalMagicLink, requestPortalMagicLink, setPortalSession } from '@/lib/portalAuth';
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [selected, setSelected] = useState<DemoAccount>(DEMO_ACCOUNTS[0]);
  const [email, setEmail] = useState(DEMO_ACCOUNTS[0].email);
  const [password, setPassword] = useState(DEMO_ACCOUNTS[0].password);
  const [mfaCode, setMfaCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  function pickDemo(account: DemoAccount) {
    setSelected(account);
    setEmail(account.email);
    setPassword(account.password);
    setMfaCode('');
    setRecoveryCode('');
    setMfaRequired(false);
    setError('');
  }

  async function loginPortalDemo(account: DemoAccount) {
    try {
      const { data } = await axios.post(`${API_BASE}/client-portal/auth/demo-login`, { email: account.email });
      setPortalSession(data.access_token, { contact: data.contact, client: data.client });
      router.push('/client-portal');
      return;
    } catch {
      // Fall back to magic-link flow for environments without demo endpoint seeded.
      const link = await requestPortalMagicLink(account.email);
      if (!link.token) throw new Error('Portal demo contact is not seeded yet. Run seed_demo_data.py.');
      await confirmPortalMagicLink(link.token);
      router.push('/client-portal');
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      if (selected.auth === 'portal') {
        await loginPortalDemo(selected);
        return;
      }
      const result = await login(email, password, mfaCode, recoveryCode);
      if (result.mfaRequired) {
        setMfaRequired(true);
        setError('Enter your authenticator code or a recovery code to continue.');
        return;
      }
      const role = (result as { role?: string }).role;
      router.push(homeForRole(role) || selected.workspace);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-stone-100 text-stone-900" data-testid="login-shell">
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-[1.05fr_0.95fr]">
        <section className="border-r border-stone-300 bg-white px-6 py-10 sm:px-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-teal-800">CA Copilot · Role Workspaces</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-stone-950">Four desks. Four credentials. Clear limits.</h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-stone-600">
            Neutral banking UI with high-contrast text. Each role lands in a dedicated dashboard with only the features allowed for that tier.
          </p>

          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {DEMO_ACCOUNTS.map(account => {
              const active = selected.email === account.email;
              return (
                <button
                  key={account.email}
                  type="button"
                  onClick={() => pickDemo(account)}
                  data-testid={`demo-role-${account.tier}`}
                  className={`rounded-xl border p-4 text-left transition ${
                    active
                      ? 'border-teal-700 bg-teal-50 shadow-sm'
                      : 'border-stone-300 bg-stone-50 hover:border-stone-400'
                  }`}
                >
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">{account.label}</p>
                  <p className="mt-2 text-sm font-medium text-stone-950">{account.email}</p>
                  <p className="mt-1 font-mono text-xs text-stone-700">{account.password}</p>
                  <p className="mt-2 text-xs leading-5 text-stone-600">{account.summary}</p>
                </button>
              );
            })}
          </div>
        </section>

        <section className="flex items-center px-6 py-10 sm:px-10">
          <div className="w-full rounded-2xl border border-stone-300 bg-white p-6 shadow-sm sm:p-8">
            <div className="flex items-center gap-2 text-teal-800">
              <ShieldCheck className="h-4 w-4" />
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em]">Sign in · {selected.label}</p>
            </div>
            <h2 className="mt-2 text-2xl font-semibold text-stone-950">Enter your workspace</h2>
            <p className="mt-1 text-sm text-stone-600">
              Demo credentials are prefilled for {selected.label}. Client uses the separate portal auth context.
            </p>

            {selected.auth === 'firm' && (
              <button
                type="button"
                onClick={() => startGoogleSignIn('firm')}
                data-testid="google-signin-btn"
                className="mt-5 w-full rounded-lg border border-stone-300 bg-stone-50 px-4 py-2.5 text-sm font-medium text-stone-900"
              >
                Continue with Google
              </button>
            )}

            <form onSubmit={handleSubmit} className="mt-5 space-y-4">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  data-testid="login-email"
                  className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-950 outline-none focus:border-teal-700"
                />
              </div>
              <div>
                <label htmlFor="password" className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">
                  Password
                </label>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  data-testid="login-password"
                  className="h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-sm text-stone-950 outline-none focus:border-teal-700"
                />
              </div>

              {mfaRequired && (
                <div className="grid gap-3 rounded-lg border border-stone-300 bg-stone-50 p-3">
                  <input
                    value={mfaCode}
                    onChange={e => setMfaCode(e.target.value)}
                    data-testid="login-mfa"
                    placeholder="Authenticator code"
                    className="h-10 rounded-md border border-stone-300 px-3 text-sm"
                  />
                  <input
                    value={recoveryCode}
                    onChange={e => setRecoveryCode(e.target.value)}
                    data-testid="login-recovery"
                    placeholder="Recovery code"
                    className="h-10 rounded-md border border-stone-300 px-3 text-sm"
                  />
                </div>
              )}

              {error && (
                <p data-testid="login-error" className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-800">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit"
                className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-stone-900 text-sm font-semibold text-white disabled:opacity-60"
              >
                {loading ? 'Signing in…' : `Open ${selected.label} dashboard`}
                <ArrowRight className="h-4 w-4" />
              </button>
            </form>

            <p className="mt-5 text-center text-sm text-stone-600">
              New firm?{' '}
              <a href="/register" data-testid="register-link" className="font-medium text-teal-800 underline-offset-2 hover:underline">
                Provision a workspace
              </a>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
