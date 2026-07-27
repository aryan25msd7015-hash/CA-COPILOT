'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ChevronDown, Menu, X } from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { NAV_GROUPS } from '@/lib/navigation';

export default function FeatureNav() {
  const { user } = useAuth();
  const pathname = usePathname();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    setOpenGroup(null);
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (!navRef.current?.contains(event.target as Node)) {
        setOpenGroup(null);
        setMobileOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setOpenGroup(null);
        setMobileOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocClick);
      document.removeEventListener('keydown', onKey);
    };
  }, []);

  if (!user) return null;

  const groups = NAV_GROUPS.map(group => ({
    ...group,
    items: group.items.filter(item => item.roles.includes(user.role)),
  })).filter(group => group.items.length > 0);

  return (
    <nav ref={navRef} className="relative flex items-center gap-1" data-testid="app-feature-nav" aria-label="Features">
      {/* Desktop dropdowns */}
      <div className="hidden items-center gap-0.5 lg:flex">
        {groups.map(group => {
          const active = group.items.some(item => item.href === pathname);
          const open = openGroup === group.title;
          return (
            <div key={group.title} className="relative">
              <button
                type="button"
                aria-expanded={open}
                aria-haspopup="menu"
                data-testid={`nav-group-${group.title.toLowerCase()}`}
                onClick={() => setOpenGroup(open ? null : group.title)}
                className={`inline-flex h-9 items-center gap-1 rounded-lg px-3 text-sm font-medium transition ${
                  active || open
                    ? 'bg-[var(--accent-soft)] text-[var(--fg-0)]'
                    : 'text-[var(--fg-1)] hover:bg-[var(--bg-3)] hover:text-[var(--fg-0)]'
                }`}
              >
                {group.title}
                <ChevronDown className={`h-3.5 w-3.5 transition ${open ? 'rotate-180' : ''}`} />
              </button>
              {open && (
                <div
                  role="menu"
                  className="nav-dropdown absolute left-0 top-[calc(100%+8px)] z-50 min-w-[240px] overflow-hidden rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] p-1.5 shadow-[var(--shadow-panel)]"
                >
                  <p className="px-2.5 pb-1.5 pt-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--fg-3)]">
                    {group.title}
                  </p>
                  {group.items.map(item => {
                    const isActive = pathname === item.href;
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        role="menuitem"
                        data-testid={`nav-link-${item.href === '/' ? 'home' : item.href.slice(1)}`}
                        className={`block rounded-lg px-2.5 py-2 text-sm transition ${
                          isActive
                            ? 'bg-[var(--accent-soft)] font-semibold text-[var(--accent)]'
                            : 'text-[var(--fg-1)] hover:bg-[var(--bg-3)] hover:text-[var(--fg-0)]'
                        }`}
                      >
                        {item.label}
                      </Link>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Mobile / tablet menu */}
      <button
        type="button"
        className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--line-2)] bg-[var(--bg-0)] px-3 text-sm font-medium text-[var(--fg-1)] lg:hidden"
        aria-expanded={mobileOpen}
        data-testid="nav-mobile-toggle"
        onClick={() => setMobileOpen(value => !value)}
      >
        {mobileOpen ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
        Features
      </button>

      {mobileOpen && (
        <div className="nav-dropdown absolute left-0 right-0 top-[calc(100%+10px)] z-50 max-h-[70vh] overflow-y-auto rounded-xl border border-[var(--line-2)] bg-[var(--bg-0)] p-2 shadow-[var(--shadow-panel)] lg:hidden">
          {groups.map(group => (
            <div key={group.title} className="mb-2 last:mb-0">
              <p className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--fg-3)]">
                {group.title}
              </p>
              <div className="space-y-0.5">
                {group.items.map(item => {
                  const isActive = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      data-testid={`nav-link-${item.href === '/' ? 'home' : item.href.slice(1)}`}
                      className={`block rounded-lg px-2.5 py-2 text-sm ${
                        isActive
                          ? 'bg-[var(--accent-soft)] font-semibold text-[var(--accent)]'
                          : 'text-[var(--fg-1)] hover:bg-[var(--bg-3)]'
                      }`}
                    >
                      {item.label}
                    </Link>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </nav>
  );
}
