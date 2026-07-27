'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, CheckCircle2, ShieldCheck, Zap } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { startGoogleSignIn } from '@/lib/googleAuth';

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
      className="relative flex min-h-screen items-center justify-center px-4 py-10"
      data-testid="login-shell"
    >
      <div className="motion-pop relative grid w-full max-w-5xl overflow-hidden rounded-3xl border border-[var(--line-2)] bg-[var(--bg-0)] shadow-[var(--shadow-panel)] md:grid-cols-[0.95fr_1.05fr]">
        <section className="hidden border-r border-[var(--line-2)] bg-[var(--bg-2)] p-8 md:block">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-xl bg-[var(--accent)] text-sm font-bold text-white">
                  CA
                </span>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--accent)]">
                    Practice workspace
                  </p>
                  <h1 className="font-display text-3xl font-semibold text-[var(--fg-0)]">CA Copilot</h1>
                </div>
              </div>
              <p className="mt-6 max-w-sm text-[15px] leading-7 text-[var(--fg-2)]">
                A calm desk for compliance delivery, client follow-ups, and AI review — without the neon dashboard noise.
              </p>
              <div className="mt-8 space-y-2.5">
                {[
                  'Tenant-scoped practice modules',
                  'Server-side token revocation',
                  'Ready for mid-tier CA firms',
                ].map(item => (
                  <div
                    key={item}
                    className="flex items-center gap-3 rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] px-3 py-2.5 text-sm text-[var(--fg-1)]"
                  >
                    <CheckCircle2 className="h-4 w-4 text-[var(--accent)]" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 rounded-2xl border border-[var(--line-2)] bg-[var(--bg-0)] p-4">
              <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--accent)]">
                <ShieldCheck className="h-3.5 w-3.5" />
                Demo account
              </p>
              <dl className="mt-3 space-y-2 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-[var(--fg-3)]">Email</dt>
                  <dd className="font-mono text-[var(--fg-0)]" data-testid="demo-email-hint">{DEMO_EMAIL}</dd>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <dt className="text-[var(--fg-3)]">Password</dt>
                  <dd className="font-mono text-[var(--fg-0)]" data-testid="demo-password-hint">{DEMO_PASSWORD}</dd>
                </div>
              </dl>
            </div>
          </div>
        </section>

        <section className="relative p-6 sm:p-8">
          <div className="mx-auto max-w-md">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--accent)]">Sign in</p>
            <h2 className="mt-2 font-display text-3xl font-semibold text-[var(--fg-0)]">Welcome back</h2>
            <p className="mt-1.5 text-sm leading-6 text-[var(--fg-2)]">
              Use your firm account or load the demo credentials to explore the workspace.
            </p>

            {/* REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH */}
            <button
              type="button"
              onClick={() => startGoogleSignIn('firm')}
              data-testid="google-signin-btn"
              className="group mt-5 flex w-full items-center justify-center gap-3 rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] px-4 py-3 text-sm font-medium text-[var(--fg-0)] transition hover:bg-[var(--bg-3)]"
            >
              <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-white shadow-sm">
                <svg viewBox="0 0 48 48" className="h-4 w-4" aria-hidden="true">
                  <path fill="#4285F4" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#34A853" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/>
                  <path fill="#EA4335" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                </svg>
              </span>
              <span className="flex-1 text-left">Continue with Google</span>
              <ArrowRight className="h-4 w-4 text-[var(--fg-3)] transition group-hover:translate-x-0.5 group-hover:text-[var(--accent)]" />
            </button>

            <div className="mt-4 flex items-center gap-3">
              <span className="h-px flex-1 bg-[var(--line-2)]" />
              <span className="text-[11px] uppercase tracking-[0.16em] text-[var(--fg-3)]">Or email</span>
              <span className="h-px flex-1 bg-[var(--line-2)]" />
            </div>

            <button
              type="button"
              onClick={useDemoAccount}
              data-testid="demo-account-btn"
              className="mt-4 flex w-full items-center justify-between rounded-xl border border-[var(--accent)]/25 bg-[var(--accent-soft)] px-4 py-3 text-left text-sm font-medium text-[var(--accent)] transition hover:border-[var(--accent)]/45"
            >
              <span className="flex items-center gap-2.5">
                <Zap className="h-4 w-4" />
                <span>Use demo account</span>
              </span>
              <ArrowRight className="h-4 w-4" />
            </button>

            <form onSubmit={handleSubmit} className="mt-5 space-y-4">
              <div>
                <label htmlFor="email" className="mb-1.5 block text-[12px] font-medium text-[var(--fg-2)]">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  data-testid="login-email"
                  className="h-11 w-full rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] px-3 text-sm text-[var(--fg-0)] outline-none transition placeholder:text-[var(--fg-3)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[rgba(11,95,92,0.15)]"
                  placeholder={DEMO_EMAIL}
                />
              </div>
              <div>
                <div className="mb-1.5 flex items-center justify-between gap-3">
                  <label htmlFor="password" className="block text-[12px] font-medium text-[var(--fg-2)]">
                    Password
                  </label>
                  <a
                    href="/forgot-password"
                    className="text-[12px] font-medium text-[var(--accent)] hover:underline"
                    data-testid="forgot-password-link"
                  >
                    Forgot password?
                  </a>
                </div>
                <input
                  id="password"
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  data-testid="login-password"
                  className="h-11 w-full rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] px-3 text-sm text-[var(--fg-0)] outline-none transition placeholder:text-[var(--fg-3)] focus:border-[var(--accent)] focus:ring-2 focus:ring-[rgba(11,95,92,0.15)]"
                  placeholder={DEMO_PASSWORD}
                />
              </div>

              {mfaRequired && (
                <div className="grid gap-3 rounded-xl border border-[var(--line-2)] bg-[var(--bg-2)] p-3">
                  <div>
                    <label htmlFor="mfaCode" className="mb-1.5 block text-[12px] font-medium text-[var(--fg-2)]">
                      Authenticator code
                    </label>
                    <input
                      id="mfaCode"
                      inputMode="numeric"
                      value={mfaCode}
                      onChange={(e) => setMfaCode(e.target.value)}
                      data-testid="login-mfa"
                      className="h-11 w-full rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] px-3 font-mono text-sm text-[var(--fg-0)] outline-none"
                      placeholder="123456"
                    />
                  </div>
                  <div>
                    <label htmlFor="recoveryCode" className="mb-1.5 block text-[12px] font-medium text-[var(--fg-2)]">
                      Recovery key
                    </label>
                    <input
                      id="recoveryCode"
                      value={recoveryCode}
                      onChange={(e) => setRecoveryCode(e.target.value)}
                      data-testid="login-recovery"
                      className="h-11 w-full rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] px-3 font-mono text-sm text-[var(--fg-0)] outline-none"
                      placeholder="Optional"
                    />
                  </div>
                </div>
              )}

              {error && (
                <p
                  data-testid="login-error"
                  className="rounded-xl border border-[rgba(180,35,24,0.25)] bg-[rgba(180,35,24,0.08)] px-3 py-2 text-xs text-[var(--danger)]"
                >
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={loading}
                data-testid="login-submit"
                className="liquid-button relative flex h-11 w-full items-center justify-center gap-2 rounded-xl text-sm disabled:opacity-60"
              >
                {loading ? (
                  <>
                    <span className="ring-loader" />
                    <span>Signing in…</span>
                  </>
                ) : (
                  <>
                    <span>Enter workspace</span>
                    <ArrowRight className="h-4 w-4" />
                  </>
                )}
              </button>
            </form>

            <p className="mt-5 text-center text-sm text-[var(--fg-2)]">
              New firm?{' '}
              <a
                href="/register"
                data-testid="register-link"
                className="font-medium text-[var(--accent)] underline-offset-4 hover:underline"
              >
                Create a workspace
              </a>
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
