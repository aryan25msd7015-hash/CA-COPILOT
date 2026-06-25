'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { ArrowLeft, BadgeCheck } from 'lucide-react';
import { api } from '@/lib/api';

function VerifyEmailStatus() {
  const searchParams = useSearchParams();
  const token = searchParams.get('token') || '';
  const [status, setStatus] = useState(token ? 'Verifying email...' : 'Verification token is missing.');
  const [ok, setOk] = useState(false);

  useEffect(() => {
    if (!token) return;
    let active = true;
    api.post('/auth/email-verification/confirm', { token })
      .then(() => {
        if (!active) return;
        setOk(true);
        setStatus('Email verified. Your account recovery channel is active.');
      })
      .catch((err: unknown) => {
        if (!active) return;
        const detail = typeof err === 'object' && err && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : undefined;
        setOk(false);
        setStatus(detail || 'Could not verify email.');
      });
    return () => {
      active = false;
    };
  }, [token]);

  return (
    <p className={`mt-6 rounded-2xl px-3 py-2 text-sm ${ok ? 'bg-emerald-50 text-emerald-700' : 'bg-sky-50 text-sky-700'}`}>
      {status}
    </p>
  );
}

export default function VerifyEmailPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#f5f7fb] px-4 py-10">
      <section className="w-full max-w-md rounded-[28px] border border-white/70 bg-white/90 p-7 shadow-[0_30px_90px_rgba(15,23,42,0.16)] backdrop-blur">
        <a href="/login" className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 hover:text-slate-900">
          <ArrowLeft className="h-4 w-4" />
          Back to sign in
        </a>
        <div className="mt-6 grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
          <BadgeCheck className="h-6 w-6" />
        </div>
        <h1 className="mt-4 text-2xl font-semibold text-slate-950">Verify email</h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Confirming your address enables password recovery and security notices.
        </p>
        <Suspense fallback={null}>
          <VerifyEmailStatus />
        </Suspense>
      </section>
    </main>
  );
}
