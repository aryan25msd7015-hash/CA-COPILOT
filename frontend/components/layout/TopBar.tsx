'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Command, LogOut, Search } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { navLabelForPath } from '@/lib/navigation';
import CommandPalette from './CommandPalette';
import FeatureNav from './FeatureNav';

function initials(email: string) {
  return email
    .split('@')[0]
    .split(/[._-]/)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase())
    .join('') || 'CA';
}

export default function TopBar({ title }: { title?: string }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [commandOpen, setCommandOpen] = useState(false);
  const pageTitle = title || navLabelForPath(pathname, user?.role);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setCommandOpen(true);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  if (!user) return null;

  return (
    <>
      <header
        className="sticky top-0 z-30 border-b border-[var(--line-2)] bg-[color-mix(in_srgb,var(--bg-0)_88%,transparent)] backdrop-blur-xl"
        data-testid="app-topbar"
      >
        <div className="mx-auto flex h-[4.25rem] max-w-[1400px] items-center gap-3 px-4 sm:px-6 lg:px-8">
          <Link
            href="/"
            className="group flex shrink-0 items-center gap-2.5 outline-none"
            data-testid="brand-home-link"
          >
            <span className="grid h-9 w-9 place-items-center rounded-lg bg-[var(--accent)] text-[13px] font-bold tracking-wide text-white transition group-hover:opacity-90">
              CA
            </span>
            <span className="hidden min-w-0 sm:block">
              <span className="block font-display text-[1.05rem] font-semibold leading-none tracking-tight text-[var(--fg-0)]">
                CA Copilot
              </span>
              <span className="mt-0.5 block text-[11px] font-medium text-[var(--fg-3)]">
                Practice workspace
              </span>
            </span>
          </Link>

          <div className="mx-2 hidden h-6 w-px bg-[var(--line-2)] md:block" />

          <div className="min-w-0 flex-1">
            <FeatureNav />
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={() => setCommandOpen(true)}
              data-testid="command-palette-trigger"
              className="hidden h-9 min-w-[200px] items-center justify-between gap-3 rounded-lg border border-[var(--line-2)] bg-[var(--bg-2)] px-3 text-left text-sm text-[var(--fg-2)] transition hover:border-[var(--line-3)] hover:text-[var(--fg-1)] xl:flex"
            >
              <span className="flex items-center gap-2">
                <Search className="h-3.5 w-3.5" />
                Search modules
              </span>
              <span className="kbd">
                <Command className="h-3 w-3" /> K
              </span>
            </button>

            <button
              type="button"
              title="Open command palette"
              onClick={() => setCommandOpen(true)}
              data-testid="command-palette-mobile-trigger"
              className="grid h-9 w-9 place-items-center rounded-lg border border-[var(--line-2)] bg-[var(--bg-0)] text-[var(--fg-2)] xl:hidden"
            >
              <Search className="h-4 w-4" />
            </button>

            <div className="hidden items-center gap-2 rounded-lg border border-[var(--line-2)] bg-[var(--bg-0)] px-2.5 py-1.5 sm:flex">
              <span className="grid h-7 w-7 place-items-center rounded-md bg-[var(--bg-3)] text-[11px] font-semibold text-[var(--fg-1)]">
                {initials(user.email)}
              </span>
              <span className="min-w-0">
                <span className="block max-w-[140px] truncate text-xs font-medium text-[var(--fg-0)]">
                  {user.email}
                </span>
                <span className="block text-[10px] uppercase tracking-[0.14em] text-[var(--fg-3)]">
                  {user.role}
                </span>
              </span>
            </div>

            <button
              type="button"
              title="Sign out"
              onClick={logout}
              data-testid="signout-btn"
              className="grid h-9 w-9 place-items-center rounded-lg border border-[var(--line-2)] bg-[var(--bg-0)] text-[var(--fg-2)] transition hover:border-[var(--danger)] hover:text-[var(--danger)]"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="border-t border-[var(--line-1)] bg-[var(--bg-2)]/80">
          <div className="mx-auto flex h-10 max-w-[1400px] items-center px-4 sm:px-6 lg:px-8">
            <p className="truncate text-sm font-medium text-[var(--fg-0)]">{pageTitle}</p>
            <span className="mx-3 hidden h-3 w-px bg-[var(--line-2)] sm:block" />
            <p className="hidden truncate text-xs text-[var(--fg-3)] sm:block">
              Firm tools stay in the menus above — pick a module when you need it.
            </p>
          </div>
        </div>
      </header>
      <CommandPalette user={user} open={commandOpen} onOpenChange={setCommandOpen} />
    </>
  );
}
