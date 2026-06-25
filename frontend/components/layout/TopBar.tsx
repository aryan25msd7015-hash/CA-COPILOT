'use client';

import { useState } from 'react';
import { usePathname } from 'next/navigation';
import { Bell, Command, LogOut, Search, Sparkles } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { navLabelForPath } from '@/lib/navigation';
import CommandPalette from './CommandPalette';

export default function TopBar({ title }: { title?: string }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const [commandOpen, setCommandOpen] = useState(false);
  const pageTitle = title || navLabelForPath(pathname, user?.role);

  return (
    <>
      <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-white/70 bg-white/64 px-5 shadow-[0_1px_0_rgba(15,23,42,0.04)] backdrop-blur-2xl">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-white text-slate-950 shadow-sm ring-1 ring-slate-200/80">
            <Sparkles className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-slate-950">{pageTitle}</p>
            <p className="text-xs text-slate-500">Live workspace</p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setCommandOpen(true)}
          className="group hidden h-10 w-[min(560px,42vw)] items-center justify-between rounded-2xl border border-white/80 bg-white/72 px-3 text-left text-sm text-slate-500 shadow-sm outline-none transition hover:bg-white focus-visible:ring-4 focus-visible:ring-sky-500/20 md:flex"
        >
          <span className="flex items-center gap-2">
            <Search className="h-4 w-4 text-slate-400" />
            <span>Search, jump, or run a workflow</span>
          </span>
          <span className="flex items-center gap-1 rounded-lg border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] font-medium text-slate-500 shadow-sm">
            <Command className="h-3 w-3" /> K
          </span>
        </button>

        <div className="flex items-center gap-2">
          <button
            type="button"
            title="Open command palette"
            onClick={() => setCommandOpen(true)}
            className="grid h-10 w-10 place-items-center rounded-xl border border-white/80 bg-white/70 text-slate-500 shadow-sm outline-none transition hover:bg-white hover:text-slate-900 focus-visible:ring-4 focus-visible:ring-sky-500/20 md:hidden"
          >
            <Search className="h-4 w-4" />
          </button>
          <button
            type="button"
            title="Notifications"
            className="relative grid h-10 w-10 place-items-center rounded-xl border border-white/80 bg-white/70 text-slate-500 shadow-sm outline-none transition hover:bg-white hover:text-slate-900 focus-visible:ring-4 focus-visible:ring-sky-500/20"
          >
            <Bell className="h-4 w-4" />
            <span className="absolute right-2 top-2 h-1.5 w-1.5 rounded-full bg-blue-500" />
          </button>
          <button
            type="button"
            title="Sign out"
            onClick={logout}
            className="grid h-10 w-10 place-items-center rounded-xl border border-white/80 bg-white/70 text-slate-500 shadow-sm outline-none transition hover:bg-white hover:text-slate-900 focus-visible:ring-4 focus-visible:ring-sky-500/20"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </header>
      <CommandPalette user={user} open={commandOpen} onOpenChange={setCommandOpen} />
    </>
  );
}
