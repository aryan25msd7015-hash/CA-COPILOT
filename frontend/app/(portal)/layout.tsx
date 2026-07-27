'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getPortalToken } from '@/lib/portalAuth';

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const path = window.location.pathname;
    if (path.includes('/client-portal/login')) {
      setReady(true);
      return;
    }
    if (!getPortalToken()) {
      router.replace('/client-portal/login');
      return;
    }
    setReady(true);
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0b1020] text-sm text-cyan-200">
        Loading client portal…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top,#123,#070b16_55%)] text-slate-100">
      {children}
    </div>
  );
}
