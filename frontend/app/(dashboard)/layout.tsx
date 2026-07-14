'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import Sidebar from '@/components/layout/Sidebar';
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
      <div className="dark-shift relative flex min-h-screen items-center justify-center overflow-hidden">
        <div className="hud-panel motion-pop hud-corners rounded-2xl px-6 py-5">
          <div className="flex items-center gap-3">
            <span className="ring-loader" data-testid="workspace-loader" />
            <div>
              <p className="font-mono text-[11px] uppercase tracking-[0.28em] text-cyan-signal">Initialising</p>
              <p className="mt-0.5 text-sm font-medium text-fg">Booting workspace</p>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div
      className="dark-shift relative flex min-h-screen overflow-hidden"
      data-testid="dashboard-shell"
    >
      {/* Ambient orbs */}
      <div className="pointer-events-none absolute -left-40 top-[-8rem] h-[520px] w-[520px] rounded-full bg-cyan-500/20 blur-[140px]" />
      <div className="pointer-events-none absolute right-[-8rem] top-1/3 h-[440px] w-[440px] rounded-full bg-violet-500/20 blur-[140px]" />
      <div className="pointer-events-none absolute bottom-[-10rem] left-1/2 h-[320px] w-[320px] -translate-x-1/2 rounded-full bg-orange-500/10 blur-[120px]" />

      <Sidebar />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main
          className="app-page relative flex-1 overflow-auto px-4 py-6 sm:px-6 lg:px-8"
          data-testid="dashboard-main"
        >
          {children}
        </main>
        <VoiceAssistant />
      </div>
    </div>
  );
}
