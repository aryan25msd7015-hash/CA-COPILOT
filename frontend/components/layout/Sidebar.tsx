'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ComponentType } from 'react';
import {
  BarChart3, Bot, BriefcaseBusiness, Building2, CalendarDays, ClipboardCheck,
  FileSearch, FileText, FolderOpen, Gauge, Landmark, LayoutDashboard,
  LockKeyhole, MessageCircle, ReceiptIndianRupee, Search, ShieldCheck, ShieldAlert,
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
    <aside className="sticky top-0 z-20 flex h-screen w-72 shrink-0 flex-col border-r border-white/60 bg-white/70 shadow-[8px_0_40px_rgba(15,23,42,0.06)] backdrop-blur-2xl">
      <div className="border-b border-slate-200/60 p-4">
        <Link href="/" className="group flex items-center gap-3 rounded-xl px-1 py-1 outline-none transition focus-visible:ring-4 focus-visible:ring-sky-500/20">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[linear-gradient(180deg,#1f2937,#020617)] text-sm font-semibold text-white shadow-lg shadow-slate-900/20 transition group-hover:scale-105">
            CA
          </span>
          <span>
            <span className="block text-sm font-semibold text-slate-950">CA Copilot</span>
            <span className="text-xs text-slate-500">Practice OS + AI review</span>
          </span>
        </Link>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {NAV_GROUPS.map(group => {
          const items = group.items.filter(item => item.roles.includes(user.role));
          if (!items.length) return null;
          return (
            <div key={group.title}>
              <p className="px-2 pb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{group.title}</p>
              <div className="space-y-1">
                {items.map(item => {
                  const Icon = ICONS[item.href] || FileText;
                  const active = pathname === item.href;
                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      className={`group relative flex h-9 items-center gap-2.5 rounded-xl px-2.5 text-sm font-medium outline-none transition duration-150 focus-visible:ring-4 focus-visible:ring-sky-500/20 ${
                        active
                          ? 'bg-slate-950 text-white shadow-lg shadow-slate-900/14'
                          : 'text-slate-600 hover:bg-white/80 hover:text-slate-950 hover:shadow-sm'
                      }`}
                    >
                      <Icon className={`h-4 w-4 shrink-0 transition ${active ? 'text-white' : 'text-slate-400 group-hover:text-slate-700'}`} />
                      <span className="truncate">{item.label}</span>
                      {active && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-blue-400" />}
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      <div className="border-t border-slate-200/60 p-4">
        <div className="flex items-center gap-3 rounded-xl border border-white/80 bg-white/70 px-3 py-2 shadow-sm">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-950 text-xs font-semibold text-white shadow-sm">
            {initials(user.email)}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-xs font-medium text-slate-800">{user.email}</span>
            <span className="text-[11px] capitalize text-slate-500">{user.role}</span>
          </span>
        </div>
      </div>
    </aside>
  );
}
