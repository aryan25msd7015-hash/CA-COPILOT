'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/hooks/useAuth';
import Sidebar from '@/components/layout/Sidebar';
import TopBar from '@/components/layout/TopBar';
import VoiceAssistant from '@/components/assistant/VoiceAssistant';

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.push('/login');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f5f7fb]">
        <div className="apple-surface rounded-2xl px-5 py-4">
          <span className="text-sm font-medium text-slate-600">Loading workspace...</span>
        </div>
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="relative flex min-h-screen overflow-hidden bg-[#f5f7fb]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-[linear-gradient(120deg,rgba(10,132,255,0.16),rgba(20,184,166,0.1),rgba(255,255,255,0))]" />
      <Sidebar />
      <div className="relative flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="app-page flex-1 overflow-auto px-4 py-5 sm:px-6 lg:px-8">{children}</main>
        <VoiceAssistant />
      </div>
    </div>
  );
}
