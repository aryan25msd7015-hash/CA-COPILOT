'use client';

import { useState } from 'react';
import { BrainCircuit, Loader2, Sparkles, X } from 'lucide-react';
import { api } from '@/lib/api';

interface AiSummaryResponse {
  artifact_type: string;
  summary_markdown: string;
  provider: string;
  model: string;
  generated_at: string;
}

type ArtifactType = 'anomaly' | 'notice' | 'audit-paper';

interface Props {
  artifactType: ArtifactType;
  /** Any JSON-serialisable object describing the artifact (row from a grid, etc). */
  artifact: Record<string, unknown> | null;
  /** Called when user closes the modal. */
  onClose: () => void;
  open: boolean;
}

/**
 * "Deep AI Summary" modal — sends the artifact to Gemini 2.5-Pro via
 * `POST /api/ai/summarize/{artifactType}` and renders the structured
 * analyst brief (SIGNAL / RISK / ACTIONS / REFERENCES / DRAFT).
 */
export default function AiSummaryModal({ artifactType, artifact, onClose, open }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiSummaryResponse | null>(null);

  if (!open) return null;

  const label =
    artifactType === 'anomaly' ? 'Anomaly'
    : artifactType === 'notice' ? 'Notice'
    : 'Audit Paper';

  async function run() {
    if (!artifact) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const resp = await api.post<AiSummaryResponse>(
        `/ai/summarize/${artifactType}`,
        { artifact },
      );
      setResult(resp.data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Analysis failed';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[90vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-800 bg-slate-950 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 bg-gradient-to-r from-cyan-950/40 to-violet-950/40 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-400 to-violet-400">
              <BrainCircuit className="h-5 w-5 text-slate-950" />
            </div>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
                Deep Analyst · Gemini 2.5 Pro
              </div>
              <div className="text-lg font-semibold text-slate-100">
                {label} — AI structured summary
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-900 hover:text-slate-100"
            data-testid="btn-close-ai-summary"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {/* Artifact preview */}
          <div className="mb-4 rounded-xl border border-slate-800 bg-slate-900/50 p-3">
            <div className="mb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
              Artifact context
            </div>
            <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all text-xs text-slate-300">
{JSON.stringify(artifact, null, 2)}
            </pre>
          </div>

          {!result && !loading && !error && (
            <div className="rounded-xl border border-dashed border-slate-800 px-6 py-10 text-center">
              <Sparkles className="mx-auto h-8 w-8 text-cyan-400" />
              <p className="mt-3 text-sm text-slate-300">
                Run a deep analyst pass on this {label.toLowerCase()}. Gemini 2.5 Pro will draft a
                structured brief with signal, risk assessment, recommended actions, regulatory
                references, and a draft message you can copy-paste.
              </p>
              <button
                onClick={run}
                className="mt-4 inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-sm"
                data-testid="btn-run-ai-summary"
              >
                <BrainCircuit className="h-4 w-4" /> Run deep analysis
              </button>
            </div>
          )}

          {loading && (
            <div className="rounded-xl border border-cyan-900 bg-cyan-950/40 px-6 py-10 text-center">
              <Loader2 className="mx-auto h-8 w-8 animate-spin text-cyan-300" />
              <p className="mt-3 font-mono text-xs uppercase tracking-widest text-cyan-300">
                Deep analyst engaged · streaming reasoning through Gemini 2.5 Pro…
              </p>
              <p className="mt-1 text-xs text-slate-400">Typically takes 6–15 seconds.</p>
            </div>
          )}

          {error && (
            <div className="rounded-xl border border-rose-900 bg-rose-950/40 px-4 py-3 font-mono text-xs text-rose-300">
              {error}
              <div className="mt-2">
                <button
                  onClick={run}
                  className="rounded-lg border border-rose-800 px-2 py-1 text-xs text-rose-100 hover:bg-rose-900/40"
                >
                  Retry
                </button>
              </div>
            </div>
          )}

          {result && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
                  Result · {result.model}
                </div>
                <button
                  onClick={() => navigator.clipboard.writeText(result.summary_markdown)}
                  className="rounded-lg border border-slate-700 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-slate-300 hover:bg-slate-800"
                  data-testid="btn-copy-summary"
                >
                  Copy
                </button>
              </div>
              <MarkdownLite text={result.summary_markdown} />
              <button
                onClick={run}
                className="mt-4 inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-800"
              >
                <BrainCircuit className="h-3.5 w-3.5" /> Re-run analysis
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Tiny markdown renderer — enough to make **bold**, headings, and bullets
 * look clean. Avoids a heavy dep.
 */
function MarkdownLite({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-2 text-sm leading-relaxed text-slate-200">
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={i} className="h-1" />;
        // Headings via **HEADING** — as the deep analyst prompt uses
        if (/^\*\*[A-Z].*\*\*\s*(—|-)?/.test(trimmed)) {
          return (
            <div key={i} className="mt-3 font-mono text-[11px] uppercase tracking-widest text-cyan-400">
              {trimmed.replace(/\*\*/g, '').replace(/\s*(—|-)\s*$/, '')}
            </div>
          );
        }
        // Bullets
        if (/^[*\-]\s+/.test(trimmed)) {
          return (
            <div key={i} className="flex gap-2 pl-2">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-cyan-400" />
              <span dangerouslySetInnerHTML={{ __html: inlineBold(trimmed.replace(/^[*\-]\s+/, '')) }} />
            </div>
          );
        }
        // Numbered list
        if (/^\d+\.\s+/.test(trimmed)) {
          const [num, ...rest] = trimmed.split(/\.\s+/);
          return (
            <div key={i} className="flex gap-2 pl-2">
              <span className="w-6 shrink-0 font-mono text-xs text-cyan-400">{num}.</span>
              <span dangerouslySetInnerHTML={{ __html: inlineBold(rest.join('. ')) }} />
            </div>
          );
        }
        return (
          <p key={i} dangerouslySetInnerHTML={{ __html: inlineBold(trimmed) }} />
        );
      })}
    </div>
  );
}

function inlineBold(s: string): string {
  return s.replace(/\*\*(.+?)\*\*/g, '<strong class="text-slate-50">$1</strong>');
}
