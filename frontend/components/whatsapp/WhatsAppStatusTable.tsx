'use client';

import { useState } from 'react';
import type { ColDef, ICellRendererParams } from 'ag-grid-community';
import { api } from '@/lib/api';
import { usePermission } from '@/hooks/usePermission';
import DataGrid from '@/components/shared/DataGrid';
import StatusBadge from '@/components/shared/StatusBadge';

interface PendingFiling { filing_name: string; period: string; deadline: string; status: string; }
interface WhatsAppStatus {
  client_id: string;
  name: string;
  whatsapp_number: string;
  consent: boolean;
  consent_at?: string;
  consent_status: string;
  reminder_total: number;
  reminder_sent: number;
  reminder_failed: number;
  last_reminder_id?: string;
  last_reminder_status?: string;
  last_reminder_at?: string;
  last_template?: string;
  last_provider_mode?: string;
  last_provider_message_id?: string;
  last_error_message?: string;
  last_failed_at?: string;
  pending_filings: PendingFiling[];
}

export default function WhatsAppStatusTable({ rows, onRefresh }: { rows: WhatsAppStatus[]; onRefresh?: () => void }) {
  const canSend = usePermission('send:whatsapp_manual');
  const [message, setMessage] = useState('');

  async function send(row: WhatsAppStatus) {
    const first = row.pending_filings?.[0];
    const messageBody = first
      ? `Reminder: please share documents for ${first.filing_name} (${first.period}) before ${first.deadline}.`
      : 'Please share the pending compliance documents with our office.';
    const response = await api.post('/whatsapp/send-manual', {
      client_id: row.client_id,
      message: messageBody,
    });
    setMessage(`Manual reminder ${response.data.status} for ${row.name}.`);
    onRefresh?.();
  }

  async function copyConsentLink(clientId: string) {
    const response = await api.post(`/whatsapp/consent-link/${clientId}`);
    await navigator.clipboard.writeText(response.data.consent_url);
    setMessage(`Consent link copied. Expires ${new Date(response.data.expires_at).toLocaleString('en-IN')}.`);
  }

  const columns: ColDef<WhatsAppStatus>[] = [
    { field: 'name', headerName: 'Client', minWidth: 180 },
    { field: 'whatsapp_number', headerName: 'Number', minWidth: 150 },
    {
      field: 'consent_status',
      headerName: 'Consent',
      cellRenderer: (p: ICellRendererParams<WhatsAppStatus>) => <StatusBadge value={p.data?.consent ? 'opted_in' : 'missing_consent'} />,
    },
    { field: 'consent_at', headerName: 'Consented at', valueFormatter: p => p.value ? new Date(p.value).toLocaleString('en-IN') : '-' },
    {
      field: 'pending_filings',
      headerName: 'Pending filings',
      minWidth: 280,
      valueFormatter: p => (p.value || []).map((item: PendingFiling) => `${item.filing_name} (${item.period})`).join(', ') || 'None',
    },
    {
      field: 'reminder_total',
      headerName: 'Reminders',
      minWidth: 140,
      valueFormatter: p => `${p.data?.reminder_sent || 0} sent / ${p.data?.reminder_failed || 0} failed`,
    },
    {
      field: 'last_reminder_status',
      headerName: 'Last status',
      minWidth: 130,
      cellRenderer: (p: ICellRendererParams<WhatsAppStatus>) => <StatusBadge value={p.data?.last_reminder_status || 'pending'} />,
    },
    { field: 'last_template', headerName: 'Last template', valueFormatter: p => String(p.value || '-') },
    { field: 'last_provider_mode', headerName: 'Provider', valueFormatter: p => String(p.value || '-') },
    { field: 'last_reminder_at', headerName: 'Last reminder', valueFormatter: p => p.value ? new Date(p.value).toLocaleString('en-IN') : '-' },
    {
      field: 'last_error_message',
      headerName: 'Last failure',
      minWidth: 220,
      valueFormatter: p => p.value ? String(p.value) : '-',
    },
    {
      headerName: 'Actions',
      minWidth: 210,
      sortable: false,
      filter: false,
      cellRenderer: (p: ICellRendererParams<WhatsAppStatus>) => <div className="flex h-full items-center gap-3">
        {!p.data?.consent && <button onClick={() => p.data && copyConsentLink(p.data.client_id)} className="text-xs text-blue-700">Copy consent link</button>}
        {p.data?.consent && <button disabled={!canSend} onClick={() => p.data && send(p.data)} className="text-xs text-blue-700 disabled:opacity-40">Send reminder</button>}
      </div>,
    },
  ];

  return <div className="space-y-3">{message && <p className="text-sm text-green-700">{message}</p>}<DataGrid rows={rows} columns={columns} /></div>;
}
