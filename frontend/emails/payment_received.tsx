import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface PaymentReceivedProps {
  client_name: string;
  invoice_no: string;
  amount_inr: number;
  paid_at: string;
  method?: string;
  receipt_url?: string;
}

const fmt = (n: number) => `\u20B9${n.toLocaleString('en-IN')}`;

export const PaymentReceived: React.FC<PaymentReceivedProps> = ({
  client_name,
  invoice_no,
  amount_inr,
  paid_at,
  method = 'Razorpay',
  receipt_url,
}) => (
  <HudShell
    eyebrow="Billing · Payment Confirmed"
    headline={`Payment received from ${client_name}.`}
    preview={`${fmt(amount_inr)} received against ${invoice_no}`}
  >
    <HudParagraph>
      We&apos;ve confirmed payment against invoice {invoice_no}. Ledger updated, receipt filed, thank-you sent.
    </HudParagraph>
    <HudPanel>
      <HudFactRow label="Invoice" value={invoice_no} />
      <HudFactRow label="Amount received" value={fmt(amount_inr)} tone="good" />
      <HudFactRow label="Method" value={method} />
      <HudFactRow label="Timestamp" value={paid_at} />
    </HudPanel>
    {receipt_url && <HudCta href={receipt_url} label="Download receipt" />}
    <HudParagraph muted>
      A copy of this receipt has been mirrored to your accounting ledger and the client portal.
    </HudParagraph>
  </HudShell>
);

export const subject = (p: PaymentReceivedProps) =>
  `Payment received \u00B7 ${fmt(p.amount_inr)} \u00B7 ${p.invoice_no}`;

export default PaymentReceived;
