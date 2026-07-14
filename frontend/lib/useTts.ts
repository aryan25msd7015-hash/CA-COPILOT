'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

const BACKEND_URL =
  (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
  process.env.NEXT_PUBLIC_API_URL ||
  '';

function apiUrl(path: string): string {
  const base = BACKEND_URL.replace(/\/+$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  if (base.endsWith('/api') && suffix.startsWith('/api/')) {
    return base + suffix.slice(4);
  }
  return base + suffix;
}

export type VoiceSurface = 'friday' | 'read_aloud';

export interface UseTtsOptions {
  surface?: VoiceSurface;
  voiceId?: string;
  modelId?: string;
  /** If true, the resulting <audio> element auto-plays as soon as the blob is ready. */
  autoplay?: boolean;
}

interface TtsState {
  playing: boolean;
  loading: boolean;
  dryRun: boolean;
  error: string | null;
}

/**
 * Fetches synthesized speech from `/api/voice/tts` and plays it back
 * through a shared HTMLAudioElement. Handles concurrent calls by
 * cancelling any in-flight synthesis / playback.
 */
export function useTts(defaults: UseTtsOptions = {}) {
  const [state, setState] = useState<TtsState>({
    playing: false,
    loading: false,
    dryRun: false,
    error: null,
  });
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Lazily create a single audio element per hook instance
  const ensureAudio = useCallback((): HTMLAudioElement => {
    if (!audioRef.current) {
      const el = new Audio();
      el.preload = 'auto';
      el.addEventListener('ended', () => {
        setState((s) => ({ ...s, playing: false }));
      });
      el.addEventListener('pause', () => {
        setState((s) => ({ ...s, playing: false }));
      });
      el.addEventListener('playing', () => {
        setState((s) => ({ ...s, playing: true }));
      });
      audioRef.current = el;
    }
    return audioRef.current;
  }, []);

  const stop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setState((s) => ({ ...s, playing: false, loading: false }));
  }, []);

  const speak = useCallback(
    async (text: string, override: UseTtsOptions = {}) => {
      if (!text.trim()) return;
      stop(); // cancel anything currently playing / loading
      const audio = ensureAudio();

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setState({ playing: false, loading: true, dryRun: false, error: null });

      try {
        const resp = await fetch(apiUrl('/api/voice/tts'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(typeof window !== 'undefined' &&
            localStorage.getItem('access_token')
              ? { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
              : {}),
          },
          signal: ctrl.signal,
          body: JSON.stringify({
            text,
            surface: override.surface || defaults.surface || 'read_aloud',
            voice_id: override.voiceId || defaults.voiceId,
            model_id: override.modelId || defaults.modelId,
          }),
        });
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        const dryRun = resp.headers.get('X-Voice-DryRun') === 'true';
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        // Clean up previous object URL before assigning new one
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = url;
        audio.src = url;
        setState({ playing: false, loading: false, dryRun, error: null });
        if (defaults.autoplay !== false) {
          try {
            await audio.play();
          } catch (e) {
            // Autoplay might be blocked by browser policy — expose error but
            // keep the audio ready so a user-gesture play() succeeds.
            const msg = e instanceof Error ? e.message : 'Playback blocked';
            setState((s) => ({ ...s, error: msg }));
          }
        }
      } catch (e: unknown) {
        if ((e as { name?: string }).name === 'AbortError') return;
        const msg = e instanceof Error ? e.message : 'TTS failed';
        setState({ playing: false, loading: false, dryRun: false, error: msg });
      } finally {
        abortRef.current = null;
      }
    },
    [defaults.surface, defaults.voiceId, defaults.modelId, defaults.autoplay, ensureAudio, stop],
  );

  useEffect(() => {
    return () => {
      // Cleanup on unmount
      if (abortRef.current) abortRef.current.abort();
      if (audioRef.current) audioRef.current.pause();
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    };
  }, []);

  return { ...state, speak, stop };
}
