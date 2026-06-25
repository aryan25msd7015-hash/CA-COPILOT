'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, ShieldCheck, Sparkles } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';

const DEMO_EMAIL = 'demo@cacopilot.example.com';
const DEMO_PASSWORD = 'DemoPass123';

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [recoveryCode, setRecoveryCode] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const result = await login(email, password, mfaCode, recoveryCode);
      if (result.mfaRequired) {
        setMfaRequired(true);
        setError('Enter your authenticator code or a recovery code to continue.');
        return;
      }
      router.push('/');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  function useDemoAccount() {
    setEmail(DEMO_EMAIL);
    setPassword(DEMO_PASSWORD);
    setMfaCode('');
    setRecoveryCode('');
    setMfaRequired(false);
    setError('');
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-[#f5f7fb] px-4 py-8">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-80 bg-[linear-gradient(120deg,rgba(10,132,255,0.18),rgba(20,184,166,0.12),rgba(255,255,255,0))]" />
      <div className="relative grid w-full max-w-5xl overflow-hidden rounded-[28px] border border-white/70 bg-white/78 shadow-[0_30px_90px_rgba(15,23,42,0.18)] backdrop-blur-2xl md:grid-cols-[.95fr_1.05fr]">
        <section className="hidden border-r border-white/70 bg-slate-950 p-8 text-white md:block">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-white/12 text-white shadow-sm ring-1 ring-white/20">
                <Sparkles className="h-5 w-5" />
              </div>
              <h1 className="mt-6 text-3xl font-semibold">CA Copilot</h1>
              <p className="mt-2 max-w-sm text-sm leading-6 text-slate-300">
                Practice operations, compliance delivery, client follow-ups, and AI review in one workspace.
              </p>
              <div className="mt-8 space-y-3">
                {['2,000 company test passed', 'Server-side token revocation', 'Full practice modules live'].map(item => (
                  <div key={item} className="flex items-center gap-3 text-sm text-slate-200">
                    <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/10 p-4 backdrop-blur">
              <p className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-300">
                <ShieldCheck className="h-4 w-4" />
                Demo account
              </p>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-400">ID</dt>
                  <dd className="font-mono text-white">{DEMO_EMAIL}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-slate-400">Password</dt>
                  <dd className="font-mono text-white">{DEMO_PASSWORD}</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>

        <section className="bg-white/88 p-6 sm:p-8">
          <div className="mx-auto max-w-md">
            <div className="mb-6 md:hidden">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-slate-950 text-white shadow-sm">
                <Sparkles className="h-5 w-5" />
              </div>
            </div>
            <h2 className="text-2xl font-semibold text-slate-950">Sign in</h2>
            <p className="mt-1 text-sm text-slate-500">Use your firm account or fill the demo credentials for manual testing.</p>

            <button
              type="button"
              onClick={useDemoAccount}
              className="mt-5 flex w-full items-center justify-between rounded-2xl border border-sky-200 bg-sky-50 px-3 py-2.5 text-left text-sm font-medium text-sky-700 outline-none transition hover:border-sky-300 hover:bg-sky-100 focus-visible:ring-4 focus-visible:ring-sky-500/20"
            >
              <span>Use demo account</span>
              <ArrowRight className="h-4 w-4" />
            </button>

            <form onSubmit={handleSubmit} className="mt-5 space-y-4">
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
                  placeholder={DEMO_EMAIL}
                />
              </div>
              <div>
                <div className="mb-1 flex items-center justify-between gap-3">
                  <label htmlFor="password" className="block text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <a href="/forgot-password" className="text-xs font-medium text-sky-600 hover:underline">
                    Forgot password?
                  </a>
                </div>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="h-11 w-full rounded-2xl border border-slate-200 bg-slate-50/80 px-3 text-sm outline-none transition focus:border-sky-400 focus:bg-white focus:ring-4 focus:ring-sky-500/10"
                  placeholder={DEMO_PASSWORD}
                />
              </div>
              {mfaRequired && (
                <div className="grid gap-3 rounded-2xl border border-sky-100 bg-sky-50/70 p-3">
                  <div>
                    <label htmlFor="mfaCode" className="mb-1 block text-sm font-medium text-slate-700">
                      Authenticator code
                    </label>
                    <input
                      id="mfaCode"
                      inputMode="numeric"
                      value={mfaCode}
                      onChange={(e) => setMfaCode(e.target.value)}
                      className="h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-500/10"
                      placeholder="123456"
                    />
                  </div>
                  <div>
                    <label htmlFor="recoveryCode" className="mb-1 block text-sm font-medium text-slate-700">
                      Recovery code
                    </label>
                    <input
                      id="recoveryCode"
                      value={recoveryCode}
                      onChange={(e) => setRecoveryCode(e.target.value)}
                      className="h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 text-sm outline-none transition focus:border-sky-400 focus:ring-4 focus:ring-sky-500/10"
                      placeholder="Optional"
                    />
                  </div>
                </div>
              )}
              {error && <p className="rounded-2xl bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
              <button
                type="submit"
                disabled={loading}
                className="liquid-button h-11 w-full rounded-2xl text-sm font-medium text-white outline-none transition focus-visible:ring-4 focus-visible:ring-sky-500/20 disabled:opacity-50"
              >
                {loading ? 'Signing in...' : 'Sign in'}
              </button>
            </form>

            <p className="mt-4 text-center text-sm text-slate-500">
              Don&apos;t have an account?{' '}
              <a href="/register" className="font-medium text-sky-600 hover:underline">
                Register your firm
              </a>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
