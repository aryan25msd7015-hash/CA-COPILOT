'use client';

import Link from 'next/link';
import { ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { LogOut } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { NAV_GROUPS, NavItem } from '@/lib/navigation';
import { TIER_LABELS } from '@/lib/permissions';

interface RoleShellProps {
  title: string;
  subtitle: string;
  accent: 'partner' | 'ca' | 'staff';
  children: ReactNode;
  allowedFeatures?: string[];
}

const ACCENT = {
  partner: {
    bar: 'bg-teal-700',
    chip: 'bg-teal-50 text-teal-900 border-teal-200',
    link: 'text-teal-800',
  },
  ca: {
    bar: 'bg-slate-800',
    chip: 'bg-slate-100 text-slate-900 border-slate-300',
    link: 'text-slate-800',
  },
  staff: {
    bar: 'bg-stone-700',
    chip: 'bg-stone-100 text-stone-900 border-stone-300',
    link: 'text-stone-800',
  },
};

export default function RoleShell({ title, subtitle, accent, children, allowedFeatures }: RoleShellProps) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const theme = ACCENT[accent];

  const items: Array<NavItem & { group: string }> = NAV_GROUPS.flatMap(group =>
    group.items
      .filter(item => user && item.roles.includes(user.role))
      .filter(item => !allowedFeatures || allowedFeatures.includes(item.feature))
      .map(item => ({ ...item, group: group.title })),
  ).slice(0, 10);

  return (
    <div className="role-neutral min-h-screen bg-stone-100 text-stone-900" data-testid={`role-shell-${accent}`}>
      <div className={`h-1.5 w-full ${theme.bar}`} />
      <header className="border-b border-stone-300 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-4 sm:px-6">
          <div>
            <p className={`inline-flex rounded-full border px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-[0.14em] ${theme.chip}`}>
              {user ? TIER_LABELS[user.role] : 'Workspace'}
            </p>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-stone-950">{title}</h1>
            <p className="mt-1 max-w-2xl text-sm text-stone-600">{subtitle}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => router.push('/')}
              className="rounded-md border border-stone-300 bg-white px-3 py-2 text-xs font-medium text-stone-800"
            >
              Open full modules
            </button>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-1.5 rounded-md border border-stone-300 bg-stone-50 px-3 py-2 text-xs font-medium text-stone-800"
            >
              <LogOut className="h-3.5 w-3.5" />
              Sign out
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 pb-3 sm:px-6">
          {items.map(item => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-md border px-3 py-1.5 text-xs font-medium ${
                  active
                    ? 'border-stone-800 bg-stone-900 text-white'
                    : 'border-stone-300 bg-white text-stone-700 hover:bg-stone-50'
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">{children}</main>
    </div>
  );
}
