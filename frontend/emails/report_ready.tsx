import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface ReportReadyProps {
  client_name: string;
  report_name: string;
  period: string;
  headline_metric?: { label: string; value: string; tone?: 'good' | 'warn' | 'bad' };
  view_url: string;
}

export const ReportReady: React.FC<ReportReadyProps> = ({
  client_name,
  report_name,
  period,
  headline_metric,
  view_url,
}) => (
  <HudShell
    eyebrow="Portal · Report Ready"
    headline={`${report_name} is ready for ${client_name}.`}
    preview={`${report_name} \u2014 ${period} \u2014 ready in your portal`}
  >
    <HudParagraph>
      Your CA has published a fresh report. Full breakdown, drill-throughs, and export options are inside the portal.
    </HudParagraph>
    <HudPanel>
      <HudFactRow label="Report" value={report_name} />
      <HudFactRow label="Period" value={period} />
      {headline_metric && (
        <HudFactRow
          label={headline_metric.label}
          value={headline_metric.value}
          tone={headline_metric.tone || 'good'}
        />
      )}
    </HudPanel>
    <HudCta href={view_url} label="View report" />
  </HudShell>
);

export const subject = (p: ReportReadyProps) =>
  `Your CA report is ready \u00B7 ${p.report_name} \u00B7 ${p.period}`;

export default ReportReady;
