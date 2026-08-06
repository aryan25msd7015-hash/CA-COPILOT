'use client';

import { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import VoiceAssistant from '@/components/assistant/VoiceAssistant';
import RoleShell from '@/components/layout/RoleShell';
import { homeForRole } from '@/lib/demoAccounts';
import {
  absoluteHomeForRole,
  DESK_CONFIG,
  deskMatchesUserRole,
  getBrowserDesk,
  type AppDesk,
} from '@/lib/roleDomains';

const DESK_SHELL: Record<Exclude<AppDesk, 'hub' | 'client'>, { title: string; subtitle: string; accent: 'partner' | 'ca' | 'staff'; role: 'partner' | 'manager' | 'article' }> = {
  partner: {
    title: 'Firm Head Command Deck',
    subtitle: 'Partner-only domain. Firm-wide oversight, CA staffing, and partner controls.',
    accent: 'partner',
    role: 'partner',
  },
  manager: {
    title: 'CA Manager Desk',
    subtitle: 'CA-only domain. Assigned clients, reviews, and sign-off work.',
    accent: 'ca',
    role: 'manager',
  },
  article: {
    title: 'Intern / Staff Workbench',
    subtitle: 'Staff-only domain. Execution queue without approvals or partner lock-downs.',
    accent: 'staff',
    role: 'article',
  },
};

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const desk = getBrowserDesk();
  const isRoleWorkspace = pathname.startsWith('/workspaces/');
  const isDomainBound = desk === 'partner' || desk === 'manager' || desk === 'article';
  const isWorkspaceHome =
    pathname === '/workspaces/partner' || pathname === '/workspaces/ca' || pathname === '/workspaces/staff';

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  useEffect(() => {
    if (isLoading || !user) return;
    if (isDomainBound && !deskMatchesUserRole(desk, user.role)) {
      router.replace('/login?error=wrong_desk');
      return;
    }
    if (pathname === '/') {
      const absolute = absoluteHomeForRole(user.role);
      if (absolute && desk === 'hub') {
        window.location.assign(absolute);
        return;
      }
      router.replace(homeForRole(user.role));
    }
  }, [isLoading, user, pathname, router, desk, isDomainBound]);

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

  // Workspace home pages already wrap RoleShell themselves.
  if (isRoleWorkspace && isWorkspaceHome) {
    return <div className="min-h-screen bg-stone-100 text-stone-900">{children}</div>;
  }

  // Domain-bound module pages: stay inside the role chrome, never the shared sidebar.
  if (isDomainBound) {
    const shell = DESK_SHELL[desk];
    const config = DESK_CONFIG[desk];
    return (
      <RoleShell
        title={shell.title}
        subtitle={shell.subtitle}
        accent={shell.accent}
        allowedFeatures={config.features}
        domainBound
        expectedRole={shell.role}
      >
        {children}
      </RoleShell>
    );
  }

  // Path-based workspace deep-links without domain map still use bare content.
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
