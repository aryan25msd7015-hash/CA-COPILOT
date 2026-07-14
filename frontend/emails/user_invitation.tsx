import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface UserInvitationProps {
  invitee_name?: string;
  inviter_name?: string;
  workspace_name?: string;
  role?: string;
  accept_url: string;
}

export const UserInvitation: React.FC<UserInvitationProps> = ({
  invitee_name = 'there',
  inviter_name = 'Priya · Partner',
  workspace_name = 'Nova & Partners LLP',
  role = 'Manager',
  accept_url,
}) => (
  <HudShell
    eyebrow="Team · Invitation"
    headline={`${inviter_name} pulled you into ${workspace_name}.`}
    preview={`You've been invited to join ${workspace_name} on CA Copilot.`}
  >
    <HudParagraph>
      Hey {invitee_name} — you&apos;ve been added to the practice workspace. Accept the invite to spin up your seat, set your access key, and drop into the command deck.
    </HudParagraph>
    <HudCta href={accept_url} label="Accept invitation" />
    <HudPanel>
      <HudFactRow label="Firm" value={workspace_name} />
      <HudFactRow label="Role" value={role} />
      <HudFactRow label="Invited by" value={inviter_name} />
      <HudFactRow label="Expires" value="7 days" tone="warn" />
    </HudPanel>
    <HudParagraph muted>
      Not expecting this? Just ignore the message — the invite will lapse silently and no seat will be provisioned.
    </HudParagraph>
  </HudShell>
);

export const subject = (p: UserInvitationProps) =>
  `You've been invited to ${p.workspace_name || 'CA Copilot'} on CA Copilot`;

export default UserInvitation;
