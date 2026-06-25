'use client';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import PageHeader from '@/components/shared/PageHeader';
import WhatsAppStatusTable from '@/components/whatsapp/WhatsAppStatusTable';

export default function WhatsAppPage() {
  const query = useQuery({ queryKey: ['whatsapp-status'], queryFn: () => api.get('/whatsapp/status').then(r => r.data) });
  return <div className="space-y-5"><PageHeader title="WhatsApp Operations" subtitle="Track consent, pending filings, and reminder activity." /><WhatsAppStatusTable rows={query.data || []} onRefresh={() => query.refetch()} /></div>;
}
