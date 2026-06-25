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
      if (!open || typing && event.key !== 'Escape') return;
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
    <div className="fixed inset-0 z-50 bg-slate-950/30 px-4 py-[12vh] backdrop-blur-sm" onMouseDown={() => onOpenChange(false)}>
      <div
        className="motion-pop mx-auto max-w-2xl overflow-hidden rounded-xl border border-white/70 bg-white shadow-2xl ring-1 ring-slate-950/10"
        onMouseDown={event => event.stopPropagation()}
      >
        <div className="flex items-center gap-3 border-b border-slate-200 px-4 py-3">
          <Search className="h-4 w-4 text-slate-400" />
          <input
            ref={inputRef}
            value={query}
            onChange={event => setQuery(event.target.value)}
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
            className="h-8 flex-1 border-0 bg-transparent text-sm text-slate-950 outline-none placeholder:text-slate-400"
          />
          <button
            type="button"
            title="Close command palette"
            onClick={() => onOpenChange(false)}
            className="grid h-7 w-7 place-items-center rounded-md text-slate-400 outline-none transition hover:bg-slate-100 hover:text-slate-700 focus-visible:ring-2 focus-visible:ring-blue-500"
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
                  active ? 'bg-slate-950 text-white shadow-sm' : 'text-slate-700 hover:bg-slate-100'
                }`}
              >
                <span className={`grid h-8 w-8 shrink-0 place-items-center rounded-md ${active ? 'bg-white/10' : 'bg-slate-100'}`}>
                  <Command className={`h-4 w-4 ${active ? 'text-white' : 'text-slate-500'}`} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{item.label}</span>
                  <span className={`text-xs ${active ? 'text-slate-300' : 'text-slate-400'}`}>{item.group}{current ? ' / current' : ''}</span>
                </span>
                <ArrowRight className={`h-4 w-4 ${active ? 'text-white' : 'text-slate-300'}`} />
              </button>
            );
          })}
          {!filtered.length && (
            <div className="px-4 py-10 text-center">
              <p className="text-sm font-medium text-slate-800">No matching module</p>
              <p className="mt-1 text-xs text-slate-500">Try GST, billing, portal, reports, or tasks.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
