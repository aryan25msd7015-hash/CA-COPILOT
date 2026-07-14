import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface PortalInviteProps {
  contact_name: string;
  ca_firm_name?: string;
  portal_url: string;
}

export const PortalInvite: React.FC<PortalInviteProps> = ({
  contact_name,
  ca_firm_name = 'Nova & Partners LLP',
  portal_url,
}) => (
  <HudShell
    eyebrow="Portal · Access Granted"
    headline={`${ca_firm_name} opened a secure portal for you.`}
    preview={`${ca_firm_name} invited you to their secure client portal.`}
  >
    <HudParagraph>
      Hi {contact_name}, your CA firm has provisioned a private portal for you. Uploads, invoices, reports, and messages — all in one place, all encrypted.
    </HudParagraph>
    <HudCta href={portal_url} label="Enter portal" />
    <HudPanel>
      <HudFactRow label="Firm" value={ca_firm_name} />
      <HudFactRow label="Access" value="Active" tone="good" />
      <HudFactRow label="Security" value="E2E encrypted" />
    </HudPanel>
    <HudParagraph muted>
      No password required — the link is signed for you. Bookmark it or come back through this email whenever you need.
    </HudParagraph>
  </HudShell>
);

export const subject = (p: PortalInviteProps) =>
  `You've been invited to ${p.ca_firm_name || 'your CA'}\u2019s secure portal`;

export default PortalInvite;
