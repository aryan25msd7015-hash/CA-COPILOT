'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import VoiceAssistant from '@/components/assistant/VoiceAssistant';
import { homeForRole } from '@/lib/demoAccounts';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const isRoleWorkspace = pathname.startsWith('/workspaces/');

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  useEffect(() => {
    if (!isLoading && user && pathname === '/') {
      router.replace(homeForRole(user.role));
    }
  }, [isLoading, user, pathname, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-100 text-stone-900">
        <div className="rounded-xl border border-stone-300 bg-white px-6 py-5 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-teal-800">Initialising</p>
          <p className="mt-1 text-sm font-medium text-stone-900">Booting workspace</p>
        </div>
      </div>
    );
  }

  if (!user) return null;

  if (isRoleWorkspace) {
    return <div className="min-h-screen bg-stone-100 text-stone-900">{children}</div>;
  }

  return (
    <div
      className="dark-shift relative flex min-h-screen overflow-hidden"
      data-testid="dashboard-shell"
    >
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
