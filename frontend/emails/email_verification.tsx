import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface EmailVerificationProps {
  user_name?: string;
  verify_url: string;
  workspace_name?: string;
}

export const EmailVerification: React.FC<EmailVerificationProps> = ({
  user_name = 'Partner',
  verify_url,
  workspace_name = 'Nova & Partners LLP',
}) => (
  <HudShell
    eyebrow="Auth · Verification"
    headline={`Confirm your identity, ${user_name}.`}
    preview="One click to bring your CA Copilot workspace online."
  >
    <HudParagraph>
      Your workspace is provisioned and waiting. Verify your email to activate access — all compliance signals go dark until we confirm you own this inbox.
    </HudParagraph>
    <HudCta href={verify_url} label="Verify email" />
    <HudPanel>
      <HudFactRow label="Workspace" value={workspace_name} />
      <HudFactRow label="Plan" value="Trial · 14 days" />
      <HudFactRow label="Access" value="Pending verification" tone="warn" />
    </HudPanel>
    <HudParagraph muted>
      This link expires in 24 hours. If you did not request access, ignore this email and no account will be created.
    </HudParagraph>
  </HudShell>
);

export const subject = (_: EmailVerificationProps) =>
  'Verify your CA Copilot email';

export default EmailVerification;
