'use client';

/**
 * Emergent Google Auth callback landing.
 *
 *  URL pattern (fragment, NOT query):
 *    /auth/callback#session_id=<sid>
 *
 * We read the fragment synchronously on mount, exchange it for our JWT via
 * `/api/auth/google/session`, then redirect into the dashboard.
 *
 * REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
 */
import { useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, CheckCircle2, Radio, ShieldCheck } from 'lucide-react';
import { exchangeGoogleSession } from '@/lib/googleAuth';

type Phase = 'processing' | 'success' | 'awaiting_approval' | 'error';

export default function GoogleAuthCallback() {
  const search = useSearchParams();
  const intent = search.get('intent') || 'firm';
  const [phase, setPhase] = useState<Phase>('processing');
  const [message, setMessage] = useState<string>('Verifying secure handshake…');
  const [email, setEmail] = useState<string | null>(null);
  const processed = useRef(false);

  useEffect(() => {
    // Guard against React StrictMode double-invoke — session_id may be exchanged only once.
    if (processed.current) return;
    processed.current = true;

    const hash = typeof window !== 'undefined' ? window.location.hash : '';
    const params = new URLSearchParams(hash.replace(/^#/, ''));
    const sid = params.get('session_id');

    if (!sid) {
      setPhase('error');
      setMessage('No session_id in URL. Restart sign-in from /login.');
      return;
    }

    (async () => {
      try {
        const res = await exchangeGoogleSession(sid);
        setEmail(res.user?.email || null);
        setPhase('success');
        setMessage('Session verified. Loading terminal…');
        // Clear the fragment before navigating so refresh doesn't re-exchange.
        window.history.replaceState(null, '', window.location.pathname);
        // Full-page navigate so the AuthProvider re-mounts and reads the new token.
        setTimeout(() => {
          window.location.href = intent === 'portal' ? '/portal' : '/';
        }, 700);
      } catch (err: unknown) {
        const detail =
          (err as { response?: { data?: { detail?: string }; status?: number } })?.response?.data?.detail ||
          (err as Error).message ||
          'Sign-in failed';
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status === 202 || String(detail).toLowerCase().includes('awaiting')) {
          setPhase('awaiting_approval');
          setMessage(detail);
        } else {
          setPhase('error');
          setMessage(detail);
        }
      }
    })();
  }, [intent]);

  return (
    <div
      className="dark-shift relative flex min-h-screen items-center justify-center overflow-hidden px-4"
      data-testid="google-callback-shell"
      style={{
        background:
          'radial-gradient(1200px 600px at 12% -10%, rgba(34, 211, 238, 0.14), transparent 55%),' +
          'radial-gradient(900px 500px at 92% 0%, rgba(167, 139, 250, 0.13), transparent 60%),' +
          'linear-gradient(180deg, #060913 0%, #080b16 42%, #05070d 100%)',
      }}
    >
      <div className="pointer-events-none absolute -left-40 top-[-8rem] h-[520px] w-[520px] rounded-full bg-cyan-500/20 blur-[140px]" />
      <div className="pointer-events-none absolute right-[-8rem] top-1/3 h-[440px] w-[440px] rounded-full bg-violet-500/20 blur-[140px]" />

      <div
        className="motion-pop relative w-full max-w-md rounded-[24px] border border-cyan-400/25 bg-[rgba(9,14,32,0.85)] p-7 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9),0_0_60px_-10px_rgba(34,211,238,0.35)] backdrop-blur-2xl"
        data-testid={`callback-phase-${phase}`}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />
        <div className="flex items-center gap-2">
          <span className="motion-blink inline-block h-1.5 w-1.5 rounded-full bg-cyan-400" />
          <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-cyan-signal">
            Handshake · Google
          </p>
        </div>
        <h1 className="mt-2 font-display text-2xl font-semibold text-fg-0">
          {phase === 'processing' && 'Verifying your identity'}
          {phase === 'success' && 'Access granted'}
          {phase === 'awaiting_approval' && 'Awaiting approval'}
          {phase === 'error' && 'Sign-in blocked'}
        </h1>
        <p className="mt-1.5 text-sm text-fg-2" data-testid="callback-message">{message}</p>
        {email && (
          <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.22em] text-fg-3">{email}</p>
        )}

        <div className="mt-6 rounded-xl border border-line bg-[rgba(6,11,26,0.7)] p-4">
          {phase === 'processing' && (
            <div className="flex items-center gap-3">
              <span className="ring-loader" />
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-cyan-signal">Signal · verifying</p>
                <p className="mt-0.5 text-xs text-fg-2">Trading session_id for JWT with the backend.</p>
              </div>
            </div>
          )}
          {phase === 'success' && (
            <div className="flex items-center gap-3">
              <span className="grid h-9 w-9 place-items-center rounded-full border border-emerald-400/50 bg-emerald-500/10">
                <CheckCircle2 className="h-4 w-4 text-emerald-300" />
              </span>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-emerald-300">Verified</p>
                <p className="mt-0.5 text-xs text-fg-2">Loading your command center…</p>
              </div>
            </div>
          )}
          {phase === 'awaiting_approval' && (
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-amber-400/50 bg-amber-500/10">
                <ShieldCheck className="h-4 w-4 text-amber-300" />
              </span>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-amber-300">Pending review</p>
                <p className="mt-0.5 text-xs text-fg-2">
                  A partner in this workspace has been notified. You&apos;ll get an email as soon as your access is approved.
                </p>
              </div>
            </div>
          )}
          {phase === 'error' && (
            <div className="flex items-start gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-rose-400/50 bg-rose-500/10">
                <AlertCircle className="h-4 w-4 text-rose-300" />
              </span>
              <div>
                <p className="font-mono text-[11px] uppercase tracking-[0.22em] text-rose-300">Blocked</p>
                <p className="mt-0.5 text-xs text-fg-2">
                  {message} — head back to <a href="/login" className="text-cyan-300 underline">the login page</a> and try again.
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="mt-5 flex items-center gap-2 text-[10px] font-medium text-fg-3">
          <Radio className="h-3 w-3 text-cyan-300 motion-blink" />
          <span className="font-mono uppercase tracking-[0.22em]">Emergent secure channel</span>
        </div>
      </div>
    </div>
  );
}
