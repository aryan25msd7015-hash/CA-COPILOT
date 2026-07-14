import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface InvoiceOverdueProps {
  client_name: string;
  invoice_no: string;
  amount_inr: number;
  days_overdue: number;
  pay_url: string;
}

const fmt = (n: number) => `\u20B9${n.toLocaleString('en-IN')}`;

export const InvoiceOverdue: React.FC<InvoiceOverdueProps> = ({
  client_name,
  invoice_no,
  amount_inr,
  days_overdue,
  pay_url,
}) => (
  <HudShell
    eyebrow="Billing · Payment Overdue"
    headline={`Reminder \u2014 ${invoice_no} is ${days_overdue} days overdue.`}
    preview={`Invoice ${invoice_no} for ${client_name} is overdue by ${days_overdue} days.`}
  >
    <HudParagraph>
      Hi {client_name}, our records show invoice {invoice_no} is still open. A quick one-tap payment link is below — the ledger will settle instantly on receipt.
    </HudParagraph>
    <HudPanel tone="bad">
      <HudFactRow label="Invoice" value={invoice_no} />
      <HudFactRow label="Amount due" value={fmt(amount_inr)} tone="bad" />
      <HudFactRow label="Days overdue" value={`${days_overdue} days`} tone="bad" />
    </HudPanel>
    <HudCta href={pay_url} label="Pay now" tone="danger" />
    <HudParagraph muted>
      Already paid? Ignore this reminder — UPI/NEFT can take a few hours to reflect. Reply if you need a hand.
    </HudParagraph>
  </HudShell>
);

export const subject = (p: InvoiceOverdueProps) =>
  `Reminder \u00B7 Invoice ${p.invoice_no} overdue`;

export default InvoiceOverdue;
