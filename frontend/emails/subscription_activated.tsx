import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface SubscriptionActivatedProps {
  workspace_name?: string;
  plan_name: string;
  amount_inr: number;
  next_charge_at?: string;
  dashboard_url: string;
}

const fmt = (n: number) => `\u20B9${n.toLocaleString('en-IN')}`;

export const SubscriptionActivated: React.FC<SubscriptionActivatedProps> = ({
  workspace_name = 'Nova & Partners LLP',
  plan_name,
  amount_inr,
  next_charge_at,
  dashboard_url,
}) => (
  <HudShell
    eyebrow="Subscription · Live"
    headline={`${plan_name} is live for ${workspace_name}.`}
    preview={`Your CA Copilot ${plan_name} plan is now active.`}
  >
    <HudParagraph>
      Payment confirmed. All {plan_name}-tier modules are unlocked — exception autopilot, notice drafter, WhatsApp collections, and the full command deck.
    </HudParagraph>
    <HudPanel>
      <HudFactRow label="Workspace" value={workspace_name} />
      <HudFactRow label="Plan" value={plan_name} tone="good" />
      <HudFactRow label="Amount" value={`${fmt(amount_inr)} / month`} />
      {next_charge_at && <HudFactRow label="Next charge" value={next_charge_at} />}
    </HudPanel>
    <HudCta href={dashboard_url} label="Open dashboard" />
  </HudShell>
);

export const subject = (p: SubscriptionActivatedProps) =>
  `Your CA Copilot ${p.plan_name} subscription is live`;

export default SubscriptionActivated;
