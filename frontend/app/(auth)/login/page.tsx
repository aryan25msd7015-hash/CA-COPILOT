'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, ExternalLink, ShieldCheck } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { startGoogleSignIn } from '@/lib/googleAuth';
import { DEMO_ACCOUNTS, DemoAccount, homeForRole } from '@/lib/demoAccounts';
import {
  absoluteHomeForRole,
  demoAccountForDesk,
  DESK_CONFIG,
  getBrowserDesk,
  getClientDomainUrls,
  type AppDesk,
} from '@/lib/roleDomains';
import { confirmPortalMagicLink, requestPortalMagicLink, setPortalSession } from '@/lib/portalAuth';
import axios from 'axios';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [desk, setDesk] = useState<AppDesk>('hub');
  const domainUrls = getClientDomainUrls();
  const deskAccount = demoAccountForDesk(desk);
  const accounts = useMemo(
    () => (desk === 'hub' ? DEMO_ACCOUNTS : deskAccount ? [deskAccount] : DEMO_ACCOUNTS),
    [desk, deskAccount],
  );
  const [selected, setSelected] = useState<DemoAccount>(DEMO_ACCOUNTS[0]);
  const [email, setEmail] = useState(DEMO_ACCOUNTS[0].email);
  const [password, setPassword] = useState(DEMO_ACCOUNTS[0].password);
  const [mfaCode, setMfaCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const resolved = getBrowserDesk();
    setDesk(resolved);
    if (typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('error') === 'wrong_desk') {
      setError('That account belongs on a different role domain. Use the matching desk link.');
    }
  }, []);

  useEffect(() => {
    const account = demoAccountForDesk(desk);
    if (!account) return;
    setSelected(account);
    setEmail(account.email);
    setPassword(account.password);
    setMfaCode('');
    setRecoveryCode('');
    setMfaRequired(false);
  }, [desk]);

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
      const absolute = absoluteHomeForRole('client');
      if (absolute && desk === 'hub') {
        window.location.assign(absolute);
        return;
      }
      router.push('/client-portal');
      return;
    } catch {
      const link = await requestPortalMagicLink(account.email);
      if (!link.token) throw new Error('Portal demo contact is not seeded yet. Run seed_demo_data.py.');
      await confirmPortalMagicLink(link.token);
      const absolute = absoluteHomeForRole('client');
      if (absolute && desk === 'hub') {
        window.location.assign(absolute);
        return;
      }
      router.push('/client-portal');
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      if (desk !== 'hub' && deskAccount && selected.tier !== deskAccount.tier) {
        throw new Error(`This domain only accepts ${DESK_CONFIG[desk as Exclude<AppDesk, 'hub'>].label} credentials.`);
      }
      if (selected.auth === 'portal') {
        if (desk !== 'hub' && desk !== 'client') {
          throw new Error('Client credentials must be used on the Client portal domain.');
        }
        await loginPortalDemo(selected);
        return;
      }
      if (desk === 'client') {
        throw new Error('Firm credentials cannot sign in on the Client domain.');
      }

      const headers: Record<string, string> = {};
      if (desk !== 'hub') {
        headers['X-Expected-Role'] = desk;
      }
      const result = await login(email, password, mfaCode, recoveryCode, headers);
      if (result.mfaRequired) {
        setMfaRequired(true);
        setError('Enter your authenticator code or a recovery code to continue.');
        return;
      }
      const role = (result as { role?: string }).role;
      if (desk !== 'hub' && role && role !== desk) {
        throw new Error(`Wrong desk. ${role} accounts must use the ${role} domain.`);
      }
      const absolute = absoluteHomeForRole(role);
      if (absolute && (desk === 'hub' || role === desk)) {
        // Hub login always jumps to the role's own domain when configured.
        if (desk === 'hub' && absolute) {
          window.location.assign(absolute);
          return;
        }
      }
      router.push(homeForRole(role) || selected.workspace);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  const isDomainBound = desk !== 'hub';
  const heading = isDomainBound
    ? `${DESK_CONFIG[desk as Exclude<AppDesk, 'hub'>].label} desk`
    : 'Four desks. Four domains. Clear limits.';

  return (
    <div className="min-h-screen bg-stone-100 text-stone-900" data-testid="login-shell" data-desk={desk}>
      <div className="mx-auto grid min-h-screen max-w-6xl lg:grid-cols-[1.05fr_0.95fr]">
        <section className="border-r border-stone-300 bg-white px-6 py-10 sm:px-10">
          <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-teal-800">
            CA Copilot · {isDomainBound ? 'Role Domain' : 'Role Directory'}
          </p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-stone-950">{heading}</h1>
          <p className="mt-3 max-w-xl text-sm leading-6 text-stone-600">
            {isDomainBound
              ? `You are on the ${DESK_CONFIG[desk as Exclude<AppDesk, 'hub'>].label} domain. Only this role can sign in here and only this desk’s features are available.`
              : 'Each role opens on its own domain after login. Pick a demo desk below, or open a role domain directly.'}
          </p>

          {desk === 'hub' && Object.keys(domainUrls).length > 0 && (
            <div className="mt-6 grid gap-2" data-testid="role-domain-directory">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-stone-500">Live role domains</p>
              {(Object.entries(domainUrls) as Array<[Exclude<AppDesk, 'hub'>, string]>).map(([key, url]) => (
                <a
                  key={key}
                  href={`${url}/login`}
                  className="inline-flex items-center justify-between rounded-lg border border-stone-300 bg-stone-50 px-3 py-2 text-sm text-stone-900 hover:border-teal-700"
                >
                  <span>{DESK_CONFIG[key].label}</span>
                  <ExternalLink className="h-3.5 w-3.5 text-stone-500" />
                </a>
              ))}
            </div>
          )}

          <div className={`mt-8 grid gap-3 ${accounts.length > 1 ? 'sm:grid-cols-2' : 'grid-cols-1'}`}>
            {accounts.map(account => {
              const active = selected.email === account.email;
              const domainUrl = domainUrls[account.tier as Exclude<AppDesk, 'hub'>];
              return (
                <button
                  key={account.email}
                  type="button"
                  onClick={() => {
                    if (desk === 'hub' && domainUrl) {
                      window.location.assign(`${domainUrl}/login`);
                      return;
                    }
                    pickDemo(account);
                  }}
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
                  {desk === 'hub' && domainUrl && (
                    <p className="mt-2 text-[11px] font-medium text-teal-800">Opens {domainUrl.replace(/^https?:\/\//, '')}</p>
                  )}
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
            <h2 className="mt-2 text-2xl font-semibold text-stone-950">
              {isDomainBound ? 'Enter this role domain' : 'Enter your workspace'}
            </h2>
            <p className="mt-1 text-sm text-stone-600">
              {isDomainBound
                ? `Only ${selected.label} credentials work on this domain.`
                : `Demo credentials are prefilled. Login sends you to that role’s domain when configured.`}
            </p>

            {selected.auth === 'firm' && desk !== 'client' && (
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

            {desk === 'hub' && (
              <p className="mt-5 text-center text-sm text-stone-600">
                New firm?{' '}
                <a href="/register" data-testid="register-link" className="font-medium text-teal-800 underline-offset-2 hover:underline">
                  Provision a workspace
                </a>
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
