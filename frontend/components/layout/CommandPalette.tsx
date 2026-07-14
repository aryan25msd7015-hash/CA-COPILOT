'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { ArrowRight, Command, Search, X } from 'lucide-react';
import { User } from '@/types';
import { navItemsForRole } from '@/lib/navigation';

interface CommandPaletteProps {
  user?: User | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export default function CommandPalette({ user, open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const items = useMemo(() => navItemsForRole(user?.role), [user?.role]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(item =>
      [item.label, item.group, item.href, ...(item.keywords || [])]
        .join(' ')
        .toLowerCase()
        .includes(needle),
    );
  }, [items, query]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        onOpenChange(!open);
        return;
      }
      if (!open || (typing && event.key !== 'Escape')) return;
      if (event.key === 'Escape') {
        event.preventDefault();
        onOpenChange(false);
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onOpenChange, open]);

  useEffect(() => {
    if (!open) return;
    setQuery('');
    setActiveIndex(0);
    window.setTimeout(() => inputRef.current?.focus(), 20);
  }, [open]);

  useEffect(() => {
    setActiveIndex(0);
  }, [query]);

  if (!open) return null;

  function go(href: string) {
    onOpenChange(false);
    router.push(href);
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 px-4 py-[12vh] backdrop-blur-md"
      onMouseDown={() => onOpenChange(false)}
      data-testid="command-palette-overlay"
    >
      <div
        className="motion-pop hud-corners mx-auto max-w-2xl overflow-hidden rounded-2xl border border-cyan-400/25 bg-[rgba(9,14,32,0.9)] shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9),0_0_40px_-10px_rgba(34,211,238,0.35)] backdrop-blur-2xl"
        onMouseDown={event => event.stopPropagation()}
      >
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/70 to-transparent" />
        <div className="flex items-center gap-3 border-b border-line px-4 py-3">
          <Search className="h-4 w-4 text-cyan-300" />
          <input
            ref={inputRef}
            value={query}
            onChange={event => setQuery(event.target.value)}
            data-testid="command-palette-input"
            onKeyDown={event => {
              if (event.key === 'ArrowDown') {
                event.preventDefault();
                setActiveIndex(index => Math.min(index + 1, filtered.length - 1));
              }
              if (event.key === 'ArrowUp') {
                event.preventDefault();
                setActiveIndex(index => Math.max(index - 1, 0));
              }
              if (event.key === 'Enter' && filtered[activeIndex]) {
                event.preventDefault();
                go(filtered[activeIndex].href);
              }
            }}
            placeholder="Search modules, reports, workflows..."
            className="h-8 flex-1 border-0 bg-transparent text-sm text-fg outline-none placeholder:text-fg-3"
          />
          <button
            type="button"
            title="Close command palette"
            onClick={() => onOpenChange(false)}
            className="grid h-7 w-7 place-items-center rounded-md text-fg-3 outline-none transition hover:bg-white/[0.06] hover:text-fg focus-visible:ring-2 focus-visible:ring-cyan-500/40"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="max-h-[420px] overflow-y-auto p-2">
          {filtered.map((item, index) => {
            const active = index === activeIndex;
            const current = pathname === item.href;
            return (
              <button
                key={item.href}
                type="button"
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => go(item.href)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left outline-none transition ${
                  active
                    ? 'bg-gradient-to-r from-cyan-500/18 to-violet-500/12 text-fg shadow-[inset_0_0_0_1px_rgba(34,211,238,0.4)]'
                    : 'text-fg-2 hover:bg-white/[0.04] hover:text-fg'
                }`}
              >
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-md ${active ? 'bg-cyan-400/15' : 'bg-white/[0.04]'}`}>
                  <Command className={`h-4 w-4 ${active ? 'text-cyan-300' : 'text-fg-3'}`} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.label}</span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">
                    {item.group}{current ? ' · current' : ''}
                  </span>
                </span>
                <ArrowRight className={`h-4 w-4 ${active ? 'text-cyan-300' : 'text-fg-3'}`} />
              </button>
            );
          })}
          {!filtered.length && (
            <div className="px-4 py-10 text-center">
              <p className="text-sm font-medium text-fg">No matching module</p>
              <p className="mt-1 font-mono text-[11px] uppercase tracking-[0.2em] text-fg-3">
                Try GST · billing · portal · reports · tasks
              </p>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-line bg-[rgba(6,10,22,0.7)] px-4 py-2 font-mono text-[10px] uppercase tracking-[0.2em] text-fg-3">
          <span>{filtered.length} matches</span>
          <span className="flex items-center gap-2">
            <span className="kbd">↑</span><span className="kbd">↓</span> navigate
            <span className="kbd">↵</span> jump
            <span className="kbd">esc</span> close
          </span>
        </div>
      </div>
    </div>
  );
}
