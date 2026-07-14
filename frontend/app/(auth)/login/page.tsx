'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, Radio, ShieldCheck, Zap } from 'lucide-react';
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
    <div
      className="dark-shift relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-8"
      data-testid="login-shell"
    >
      {/* Ambient orbs */}
      <div className="pointer-events-none absolute -left-40 top-[-8rem] h-[520px] w-[520px] rounded-full bg-cyan-500/25 blur-[140px]" />
      <div className="pointer-events-none absolute right-[-8rem] top-1/3 h-[440px] w-[440px] rounded-full bg-violet-500/25 blur-[140px]" />

      <div className="motion-pop relative grid w-full max-w-5xl overflow-hidden rounded-[24px] border border-cyan-400/25 bg-[rgba(9,14,32,0.85)] shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9),0_0_60px_-10px_rgba(34,211,238,0.35)] backdrop-blur-2xl md:grid-cols-[.95fr_1.05fr]">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-violet-400/50 to-transparent" />

        {/* LEFT · Brand HUD */}
        <section className="jarvis-panel hidden overflow-hidden border-r border-line bg-[rgba(4,7,18,0.92)] p-8 text-white md:block">
          <div className="flex h-full flex-col justify-between">
            <div className="relative">
              <div className="flex items-center gap-3">
                <span className="jarvis-launcher relative grid h-12 w-12 place-items-center overflow-hidden rounded-2xl border border-cyan-400/40 bg-[#050a18] text-white shadow-[0_0_28px_rgba(34,211,238,0.4)]">
                  <span className="jarvis-orb block h-5 w-5 rounded-full" />
                </span>
                <div>
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.32em] text-cyan-signal">
                    Intelligence Terminal
                  </p>
                  <h1 className="font-display text-3xl font-semibold tracking-wide text-fg-0">CA · COPILOT</h1>
                </div>
              </div>
              <p className="mt-6 max-w-sm text-sm leading-6 text-fg-2">
                Practice operations, compliance delivery, client follow-ups, and AI review — all piped into
                <span className="text-cyan-signal"> one command deck</span>.
              </p>

              <div className="mt-8 space-y-2.5">
                {[
                  { label: '2,000 company regression', ok: true },
                  { label: 'Server-side token revocation', ok: true },
                  { label: 'Full practice modules live', ok: true },
                ].map(item => (
                  <div
                    key={item.label}
                    className="flex items-center gap-3 rounded-lg border border-line bg-[rgba(15,22,45,0.55)] px-3 py-2 text-sm text-fg"
                  >
                    <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full border border-emerald-400/40 bg-emerald-500/10">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-300" />
                    </span>
                    <span className="font-mono text-[11px] uppercase tracking-[0.14em]">{item.label}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Demo credentials */}
            <div className="hud-corners relative mt-8 rounded-2xl border border-cyan-400/25 bg-[rgba(6,11,26,0.7)] p-4">
              <p className="flex items-center gap-2 font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
                <ShieldCheck className="h-3.5 w-3.5" />
                Demo Account · Read-Only
              </p>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <dt className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">ID</dt>
                  <dd className="font-mono text-fg-0" data-testid="demo-email-hint">{DEMO_EMAIL}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">KEY</dt>
                  <dd className="font-mono text-fg-0" data-testid="demo-password-hint">{DEMO_PASSWORD}</dd>
                </div>
              </dl>
              <div className="mt-3 flex items-center gap-2 border-t border-line pt-3 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">
                <Radio className="h-3 w-3 text-cyan-300 motion-blink" />
                Signal · Verified session
              </div>
            </div>
          </div>
        </section>

        {/* RIGHT · Form */}
        <section className="relative bg-[rgba(9,14,32,0.7)] p-6 sm:p-8">
          <div className="mx-auto max-w-md">
            <div className="mb-6 md:hidden">
              <div className="grid h-11 w-11 place-items-center rounded-2xl border border-cyan-400/40 bg-[#050a18] shadow-[0_0_20px_rgba(34,211,238,0.35)]">
                <span className="jarvis-orb h-5 w-5 rounded-full" />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="motion-blink inline-block h-1.5 w-1.5 rounded-full bg-cyan-400" />
              <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
                Access Terminal · Sign in
              </p>
            </div>
            <h2 className="mt-2 font-display text-3xl font-semibold text-fg-0">Welcome back, partner.</h2>
            <p className="mt-1.5 text-sm text-fg-2">
              Use your firm account or tap the demo capsule to explore the workspace.
            </p>

            <button
              type="button"
              onClick={useDemoAccount}
              data-testid="demo-account-btn"
              className="mt-5 flex w-full items-center justify-between rounded-xl border border-cyan-400/30 bg-cyan-500/[0.06] px-4 py-3 text-left text-sm font-medium text-cyan-100 outline-none transition hover:border-cyan-400/60 hover:bg-cyan-500/[0.1] focus-visible:ring-2 focus-visible:ring-cyan-500/40"
            >
              <span className="flex items-center gap-2.5">
                <Zap className="h-4 w-4 text-cyan-300" />
                <span>Use demo capsule</span>
                <span className="chip chip-cyan">Live</span>
              </span>
              <ArrowRight className="h-4 w-4 text-cyan-300" />
            </button>

            <form onSubmit={handleSubmit} className="mt-5 space-y-4">
              <div>
                <label htmlFor="email" className="mb-1.5 block font-mono text-[10px] font-semibold uppercase tracking-[0.24em] text-fg-3">
                  Operator ID
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="login-email"
                  className="h-11 w-full rounded-xl border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 outline-none transition placeholder:text-fg-3 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
                  placeholder={DEMO_EMAIL}
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between gap-3">
                  <label htmlFor="password" className="block font-mono text-[10px] font-semibold uppercase tracking-[0.24em] text-fg-3">
                    Access Key
                  </label>
                  <a
                    href="/forgot-password"
                    className="font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-300 hover:text-cyan-200"
                    data-testid="forgot-password-link"
                  >
                    Forgot key?
                  </a>
                </div>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password"
                  className="h-11 w-full rounded-xl border border-line bg-[rgba(6,11,26,0.7)] px-3 text-sm text-fg-0 outline-none transition placeholder:text-fg-3 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
                  placeholder={DEMO_PASSWORD}
                />
              </div>

              {mfaRequired && (
                <div className="grid gap-3 rounded-xl border border-cyan-400/25 bg-cyan-500/[0.04] p-3">
                  <div>
                    <label htmlFor="mfaCode" className="mb-1.5 block font-mono text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-signal">
                      Authenticator Code
                    </label>
                    <input
                      id="mfaCode"
                      inputMode="numeric"
                      value={mfaCode}
                      onChange={(e) => setMfaCode(e.target.value)}
                      data-testid="login-mfa"
                      className="h-11 w-full rounded-xl border border-line bg-[rgba(6,11,26,0.7)] px-3 font-mono text-sm text-fg-0 outline-none transition placeholder:text-fg-3 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
                      placeholder="123456"
                    />
                  </div>
                  <div>
                    <label htmlFor="recoveryCode" className="mb-1.5 block font-mono text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-signal">
                      Recovery Key
                    </label>
                    <input
                      id="recoveryCode"
                      value={recoveryCode}
                      onChange={(e) => setRecoveryCode(e.target.value)}
                      data-testid="login-recovery"
                      className="h-11 w-full rounded-xl border border-line bg-[rgba(6,11,26,0.7)] px-3 font-mono text-sm text-fg-0 outline-none transition placeholder:text-fg-3 focus:border-cyan-400/55 focus:ring-2 focus:ring-cyan-500/25"
                      placeholder="Optional"
                    />
                  </div>
                </div>
              )}

              {error && (
                <p
                  data-testid="login-error"
                  className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 font-mono text-xs text-rose-200"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit"
                className="liquid-button relative flex h-11 w-full items-center justify-center gap-2 rounded-xl text-sm outline-none transition focus-visible:ring-2 focus-visible:ring-cyan-500/40 disabled:opacity-60"
              >
                {loading ? (
                  <>
                    <span className="ring-loader" />
                    <span className="font-mono text-[11px] uppercase tracking-[0.22em]">Verifying…</span>
                  </>
                ) : (
                  <>
                    <span>Engage workspace</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            <p className="mt-5 text-center text-sm text-fg-2">
              New firm?{' '}
              <a
                href="/register"
                data-testid="register-link"
                className="font-medium text-cyan-300 underline-offset-4 hover:underline"
              >
                Provision a workspace
              </a>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
