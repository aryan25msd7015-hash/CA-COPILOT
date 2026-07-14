'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { Activity, Bell, Command, LogOut, Radio, Search } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { navLabelForPath } from '@/lib/navigation';
import CommandPalette from './CommandPalette';

export default function TopBar({ title }: { title?: string }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [commandOpen, setCommandOpen] = useState(false);
  const [clock, setClock] = useState<string>('');
  const pageTitle = title || navLabelForPath(pathname, user?.role);

  useEffect(() => {
    const tick = () => {
      const d = new Date();
      setClock(
        d.toLocaleTimeString('en-IN', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: false,
        }),
      );
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <>
      <header
        className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-line bg-[rgba(8,12,26,0.72)] px-5 backdrop-blur-2xl"
        data-testid="app-topbar"
      >
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-cyan-500/40 to-transparent" />

        <div className="flex min-w-0 items-center gap-3">
          <div className="hud-corners relative grid h-9 w-9 place-items-center rounded-xl border border-cyan-400/40 bg-[#050a18] shadow-[0_0_18px_rgba(34,211,238,0.35)]">
            <Radio className="h-4 w-4 text-cyan-300 motion-blink" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-display text-[15px] font-semibold uppercase tracking-wide text-fg">
              {pageTitle}
            </p>
            <div className="flex items-center gap-2 text-[10px] font-medium text-fg-3">
              <span className="motion-blink inline-block h-1.5 w-1.5 rounded-full bg-emerald-400" />
              <span className="font-mono uppercase tracking-[0.22em]">Live · Terminal</span>
              <span className="font-mono uppercase tracking-[0.22em] text-cyan-signal">IST {clock}</span>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setCommandOpen(true)}
          data-testid="command-palette-trigger"
          className="group hidden h-10 w-[min(560px,42vw)] items-center justify-between rounded-xl border border-line bg-[rgba(15,22,45,0.55)] px-3 text-left text-sm text-fg-2 shadow-inner shadow-black/20 outline-none transition hover:border-cyan-400/45 hover:text-fg focus-visible:ring-2 focus-visible:ring-cyan-500/40 md:flex"
        >
          <span className="flex items-center gap-2.5">
            <Search className="h-4 w-4 text-fg-3 group-hover:text-cyan-300" />
            <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-fg-3">Query</span>
            <span className="text-fg-2">Search modules, jump, or run a workflow</span>
          </span>
          <span className="kbd">
            <Command className="h-3 w-3" /> K
          </span>
        </button>

        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-xl border border-line bg-[rgba(15,22,45,0.55)] px-3 py-1.5 lg:flex">
            <Activity className="h-3.5 w-3.5 text-emerald-400" />
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">Queue</span>
            <span className="font-mono text-xs font-semibold text-fg">03</span>
          </div>

          <button
            type="button"
            title="Open command palette"
            onClick={() => setCommandOpen(true)}
            data-testid="command-palette-mobile-trigger"
            className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-[rgba(15,22,45,0.55)] text-fg-2 outline-none transition hover:border-cyan-400/45 hover:text-fg focus-visible:ring-2 focus-visible:ring-cyan-500/40 md:hidden"
          >
            <Search className="h-4 w-4" />
          </button>
          <button
            type="button"
            title="Notifications"
            data-testid="notifications-btn"
            className="relative grid h-10 w-10 place-items-center rounded-xl border border-line bg-[rgba(15,22,45,0.55)] text-fg-2 outline-none transition hover:border-cyan-400/45 hover:text-fg focus-visible:ring-2 focus-visible:ring-cyan-500/40"
          >
            <Bell className="h-4 w-4" />
            <span className="motion-blink absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(34,211,238,0.9)]" />
          </button>
          <button
            type="button"
            title="Sign out"
            onClick={logout}
            data-testid="signout-btn"
            className="grid h-10 w-10 place-items-center rounded-xl border border-line bg-[rgba(15,22,45,0.55)] text-fg-2 outline-none transition hover:border-rose-400/60 hover:text-rose-300 focus-visible:ring-2 focus-visible:ring-rose-500/40"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>
      <CommandPalette user={user} open={commandOpen} onOpenChange={setCommandOpen} />
    </>
  );
}
