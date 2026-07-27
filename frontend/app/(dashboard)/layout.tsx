'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import TopBar from '@/components/layout/TopBar';
import VoiceAssistant from '@/components/assistant/VoiceAssistant';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="relative flex min-h-screen items-center justify-center bg-[var(--bg-1)]">
        <div className="rounded-2xl border border-[var(--line-2)] bg-[var(--bg-0)] px-6 py-5 shadow-[var(--shadow-panel)]">
          <div className="flex items-center gap-3">
            <span className="ring-loader" data-testid="workspace-loader" />
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--fg-3)]">Loading</p>
              <p className="mt-0.5 text-sm font-medium text-[var(--fg-0)]">Opening workspace</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="relative flex min-h-screen flex-col bg-[var(--bg-1)]" data-testid="dashboard-shell">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[radial-gradient(ellipse_at_top,rgba(11,95,92,0.08),transparent_58%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,transparent_0%,rgba(232,237,242,0.55)_100%)]" />

      <TopBar />
      <main
        className="app-page relative mx-auto w-full max-w-[1400px] flex-1 px-4 py-6 sm:px-6 lg:px-8"
        data-testid="dashboard-main"
      >
        {children}
      </main>
      <VoiceAssistant />
    </div>
  );
}
