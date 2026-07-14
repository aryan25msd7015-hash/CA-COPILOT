import * as React from 'react';
import { HudShell, HudCta, HudParagraph, HudFactRow, HudPanel } from './_shell';

export interface DocumentRequestProps {
  client_name: string;
  ca_name?: string;
  document_list: string[];
  due_date: string;
  upload_url: string;
}

export const DocumentRequest: React.FC<DocumentRequestProps> = ({
  client_name,
  ca_name = 'your CA',
  document_list,
  due_date,
  upload_url,
}) => (
  <HudShell
    eyebrow="Portal · Document Request"
    headline={`${ca_name} needs a few files from ${client_name}.`}
    preview={`${document_list.length} document(s) requested \u2014 due ${due_date}`}
  >
    <HudParagraph>
      Upload the following through your secure portal. Everything is encrypted at rest, and your CA is notified the moment each file lands.
    </HudParagraph>
    <HudPanel>
      {document_list.map((doc, i) => (
        <HudFactRow key={i} label={`Doc ${(i + 1).toString().padStart(2, '0')}`} value={doc} />
      ))}
      <HudFactRow label="Due by" value={due_date} tone="warn" />
    </HudPanel>
    <HudCta href={upload_url} label="Open secure portal" />
    <HudParagraph muted>
      Portal access is limited to your workspace — no logins to remember, just click the link from this email.
    </HudParagraph>
  </HudShell>
);

export const subject = (p: DocumentRequestProps) =>
  `New document request \u00B7 ${p.client_name}`;

export default DocumentRequest;
