import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface SubscriptionCancelledProps {
  workspace_name?: string;
  plan_name: string;
  ends_at: string;
  reactivate_url: string;
}

export const SubscriptionCancelled: React.FC<SubscriptionCancelledProps> = ({
  workspace_name = 'Nova & Partners LLP',
  plan_name,
  ends_at,
  reactivate_url,
}) => (
  <HudShell
    eyebrow="Subscription · Scheduled To End"
    headline={`${plan_name} will wind down on ${ends_at}.`}
    preview={`Your ${plan_name} subscription is scheduled to end on ${ends_at}.`}
  >
    <HudParagraph>
      We received your cancellation. {plan_name} stays active until {ends_at} — you keep full access until then, then the workspace downshifts to read-only.
    </HudParagraph>
    <HudPanel tone="warn">
      <HudFactRow label="Workspace" value={workspace_name} />
      <HudFactRow label="Plan" value={plan_name} />
      <HudFactRow label="Ends" value={ends_at} tone="warn" />
    </HudPanel>
    <HudParagraph>
      Change your mind? Reactivation is instant and preserves every setting, template, and pipeline run.
    </HudParagraph>
    <HudCta href={reactivate_url} label="Reactivate subscription" />
  </HudShell>
);

export const subject = (_: SubscriptionCancelledProps) =>
  'Your CA Copilot subscription is scheduled to end';

export default SubscriptionCancelled;
