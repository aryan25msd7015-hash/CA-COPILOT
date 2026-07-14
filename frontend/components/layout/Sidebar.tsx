'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ComponentType } from 'react';
import {
  BarChart3, Bot, BriefcaseBusiness, Building2, CalendarDays, ClipboardCheck,
  FileSearch, FileText, FolderOpen, Gauge, Landmark, LayoutDashboard,
  LockKeyhole, Mail, MessageCircle, ReceiptIndianRupee, Search, ShieldCheck, ShieldAlert,
  Sparkles, Target, UploadCloud, UsersRound,
} from 'lucide-react';
import { useAuth } from '@/hooks/useAuth';
import { NAV_GROUPS } from '@/lib/navigation';

const ICONS: Record<string, ComponentType<{ className?: string }>> = {
  '/': LayoutDashboard,
  '/anomalies': ShieldAlert,
  '/audit': ClipboardCheck,
  '/autopilot': Bot,
  '/benchmarking': BarChart3,
  '/billing': ReceiptIndianRupee,
  '/certificates': FileText,
  '/clients': Building2,
  '/deadlines': CalendarDays,
  '/diagnostics': ShieldCheck,
  '/documents': FolderOpen,
  '/drawing-power': Landmark,
  '/imports': UploadCloud,
  '/invoices': FileSearch,
  '/leases': FileText,
  '/msme': ShieldAlert,
  '/notices': MessageCircle,
  '/portal': BriefcaseBusiness,
  '/query': Search,
  '/reconciliation': Gauge,
  '/reports': BarChart3,
  '/rfp': Target,
  '/secretarial': FileText,
  '/team': UsersRound,
  '/timesheets': Sparkles,
  '/vault': LockKeyhole,
  '/whatsapp': MessageCircle,
  '/work': ClipboardCheck,
  '/email-preview': Mail,
};

function initials(email: string) {
  return email
    .split('@')[0]
    .split(/[._-]/)
    .slice(0, 2)
    .map(part => part[0]?.toUpperCase())
    .join('') || 'CA';
}

export default function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();
  if (!user) return null;

  return (
    <aside
      className="sticky top-0 z-20 flex h-screen w-72 shrink-0 flex-col border-r border-line bg-[rgba(8,12,26,0.72)] backdrop-blur-2xl"
      data-testid="app-sidebar"
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-cyan-500/10 to-transparent" />
      <div className="pointer-events-none absolute right-0 top-0 h-full w-px bg-gradient-to-b from-transparent via-cyan-500/30 to-transparent" />

      <div className="relative border-b border-line px-4 py-4">
        <Link
          href="/"
          className="group flex items-center gap-3 rounded-xl px-1 py-1 outline-none transition focus-visible:ring-2 focus-visible:ring-cyan-500/40"
          data-testid="brand-home-link"
        >
          <span className="jarvis-launcher relative grid h-11 w-11 place-items-center overflow-hidden rounded-xl border border-cyan-400/40 bg-[#050a18] text-sm font-bold text-white shadow-[0_0_28px_rgba(34,211,238,0.35)] transition group-hover:scale-105">
            <span className="jarvis-orb block h-5 w-5 rounded-full" />
          </span>
          <span>
            <span className="block font-display text-[15px] font-semibold tracking-wide text-fg">CA·COPILOT</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-cyan-signal">Practice OS × AI</span>
          </span>
        </Link>
      </div>

      <nav className="relative flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map((group, gi) => {
          const items = group.items.filter(item => item.roles.includes(user.role));
          if (!items.length) return null;
          return (
            <div key={group.title}>
              <div className="mb-1.5 flex items-center gap-2 px-2">
                <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.28em] text-fg-3">
                  {String(gi + 1).padStart(2, '0')} · {group.title}
                </span>
                <span className="h-px flex-1 bg-gradient-to-r from-line to-transparent" />
              </div>
              <div className="space-y-0.5">
                {items.map(item => {
                  const Icon = ICONS[item.href] || FileText;
                  const active = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      data-testid={`nav-link-${item.href === '/' ? 'home' : item.href.slice(1)}`}
                      className={`group relative flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm font-medium outline-none transition-all duration-200 focus-visible:ring-2 focus-visible:ring-cyan-500/40 ${
                        active
                          ? 'bg-gradient-to-r from-cyan-500/18 via-cyan-400/10 to-transparent text-white shadow-[inset_0_0_0_1px_rgba(34,211,238,0.35)]'
                          : 'text-fg-2 hover:bg-white/[0.04] hover:text-fg-0'
                      }`}
                    >
                      {active && (
                        <span className="absolute -left-3 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-r-full bg-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.85)]" />
                      )}
                      <Icon
                        className={`h-4 w-4 shrink-0 transition ${
                          active ? 'text-cyan-300' : 'text-fg-3 group-hover:text-cyan-300'
                        }`}
                      />
                      <span className="truncate">{item.label}</span>
                      {active && (
                        <span className="ml-auto flex items-center gap-1">
                          <span className="motion-blink h-1.5 w-1.5 rounded-full bg-cyan-300" />
                        </span>
                      )}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      <div className="relative border-t border-line px-4 py-4">
        <div className="hud-corners flex items-center gap-3 rounded-xl border border-line bg-[rgba(15,22,45,0.55)] px-3 py-2.5">
          <span className="relative grid h-9 w-9 shrink-0 place-items-center rounded-full border border-cyan-400/50 bg-[#040814] font-mono text-[11px] font-semibold text-cyan-200 shadow-[0_0_18px_rgba(34,211,238,0.45)]">
            {initials(user.email)}
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[#08111f] bg-emerald-400" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium text-fg">{user.email}</span>
            <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-fg-3">
              {user.role} · online
            </span>
          </span>
        </div>
      </div>
    </aside>
  );
}
