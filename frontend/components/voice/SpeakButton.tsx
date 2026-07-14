'use client';

import { Loader2, Square, Volume2 } from 'lucide-react';
import { useTts, VoiceSurface } from '@/lib/useTts';

interface Props {
  text: string;
  surface?: VoiceSurface;
  label?: string;
  variant?: 'ghost' | 'chip';
  testId?: string;
}

/**
 * Compact "Read aloud" button. Streams synthesized speech from
 * `/api/voice/tts` and plays it inline. In dry-run mode the audio is
 * silent — we show a subtle "dry-run" caption so the user knows.
 */
export default function SpeakButton({
  text,
  surface = 'read_aloud',
  label,
  variant = 'ghost',
  testId,
}: Props) {
  const { speak, stop, playing, loading, dryRun, error } = useTts({ surface });

  const disabled = !text || text.trim().length === 0;
  const busy = playing || loading;

  const base =
    variant === 'chip'
      ? 'inline-flex items-center gap-1.5 rounded-full border border-cyan-800 bg-cyan-950/40 px-3 py-1 text-xs font-mono uppercase tracking-widest text-cyan-200 hover:bg-cyan-900/50 disabled:opacity-40'
      : 'inline-flex items-center gap-1 rounded-md p-1.5 text-slate-400 hover:bg-slate-800 hover:text-cyan-300 disabled:opacity-40';

  return (
    <button
      onClick={busy ? stop : () => speak(text)}
      disabled={disabled}
      className={base}
      title={
        error
          ? error
          : busy
          ? 'Stop playback'
          : dryRun
          ? 'Read aloud (dry-run — silent stub)'
          : 'Read aloud'
      }
      data-testid={testId || 'btn-speak'}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : playing ? (
        <Square className="h-4 w-4" />
      ) : (
        <Volume2 className="h-4 w-4" />
      )}
      {label && <span>{label}</span>}
      {dryRun && variant === 'chip' && (
        <span className="ml-1 rounded bg-slate-900/60 px-1 text-[9px] text-slate-500">
          DRY-RUN
        </span>
      )}
    </button>
  );
}
