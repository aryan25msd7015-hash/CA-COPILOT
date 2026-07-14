import * as React from 'react';
import { HudShell, HudCta, HudParagraph } from './_shell';

export interface PasswordResetProps {
  user_name?: string;
  reset_url: string;
  expires_in?: string;
}

export const PasswordReset: React.FC<PasswordResetProps> = ({
  user_name = 'Partner',
  reset_url,
  expires_in = '30 minutes',
}) => (
  <HudShell
    eyebrow="Auth · Reset Access Key"
    headline={`Reset your access key, ${user_name}.`}
    preview="Secure link to reset your CA Copilot password. Expires in 30 minutes."
  >
    <HudParagraph>
      We received a request to rotate the access key on your CA Copilot workspace. Click the button below to set a new one. The link expires in {expires_in}.
    </HudParagraph>
    <HudCta href={reset_url} label="Set new access key" />
    <HudParagraph muted>
      Didn&apos;t request this? Ignore this signal — your current key stays active. For safety, we&apos;ll auto-lock the account after 5 failed attempts.
    </HudParagraph>
  </HudShell>
);

export const subject = (_: PasswordResetProps) =>
  'Reset your CA Copilot access key';

export default PasswordReset;
