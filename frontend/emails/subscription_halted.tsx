import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface SubscriptionHaltedProps {
  workspace_name?: string;
  plan_name: string;
  reason?: string;
  update_payment_url: string;
}

export const SubscriptionHalted: React.FC<SubscriptionHaltedProps> = ({
  workspace_name = 'Nova & Partners LLP',
  plan_name,
  reason = 'card charge failed',
  update_payment_url,
}) => (
  <HudShell
    eyebrow="Subscription · Payment Halted"
    headline={`Payment halted for ${workspace_name}.`}
    preview={`Your ${plan_name} subscription payment failed — please update your card.`}
  >
    <HudParagraph>
      Your recurring charge on plan {plan_name} could not be processed ({reason}). Access continues in a 7-day grace window; after that the workspace goes read-only.
    </HudParagraph>
    <HudPanel tone="bad">
      <HudFactRow label="Workspace" value={workspace_name} />
      <HudFactRow label="Plan" value={plan_name} tone="bad" />
      <HudFactRow label="Reason" value={reason} tone="bad" />
      <HudFactRow label="Grace ends in" value="7 days" tone="warn" />
    </HudPanel>
    <HudCta href={update_payment_url} label="Update payment method" tone="danger" />
  </HudShell>
);

export const subject = (_: SubscriptionHaltedProps) =>
  'Action needed \u00B7 Your CA Copilot subscription payment failed';

export default SubscriptionHalted;
