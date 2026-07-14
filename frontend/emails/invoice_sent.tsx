import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface InvoiceSentProps {
  client_name: string;
  invoice_no: string;
  amount_inr: number;
  due_date: string;
  view_url: string;
  pay_url?: string;
}

const fmt = (n: number) => `\u20B9${n.toLocaleString('en-IN')}`;

export const InvoiceSent: React.FC<InvoiceSentProps> = ({
  client_name,
  invoice_no,
  amount_inr,
  due_date,
  view_url,
  pay_url,
}) => (
  <HudShell
    eyebrow="Billing · Invoice Delivered"
    headline={`Invoice ${invoice_no} for ${client_name}.`}
    preview={`${invoice_no} · ${fmt(amount_inr)} · due ${due_date}`}
  >
    <HudParagraph>
      Your invoice is live in the portal. Full breakdown, GST split, and one-tap payment link below.
    </HudParagraph>
    <HudPanel>
      <HudFactRow label="Invoice" value={invoice_no} />
      <HudFactRow label="Amount" value={fmt(amount_inr)} />
      <HudFactRow label="Due date" value={due_date} tone="warn" />
      <HudFactRow label="Status" value="Sent · awaiting payment" />
    </HudPanel>
    <HudCta href={pay_url || view_url} label={pay_url ? 'Pay invoice' : 'View invoice'} />
    <HudParagraph muted>
      Questions on line items? Reply to this email — your CA gets it directly.
    </HudParagraph>
  </HudShell>
);

export const subject = (p: InvoiceSentProps) =>
  `Invoice ${p.invoice_no} \u00B7 ${fmt(p.amount_inr)}`;

export default InvoiceSent;
