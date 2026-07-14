'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Loader2, MessageSquare, Plus, Send, Sparkles, Trash2, User as UserIcon } from 'lucide-react';
import { api } from '@/lib/api';
import PageHeader from '@/components/shared/PageHeader';
import SpeakButton from '@/components/voice/SpeakButton';

interface StarterPrompt { category: string; intent: string; prompt: string; recommended: boolean; }
interface ChatSession {
  id: string;
  title: string;
  model: string;
  provider: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}
interface ChatMessage {
  id: string;
  session_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

const BACKEND_URL =
  (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) ||
  process.env.NEXT_PUBLIC_API_URL ||
  '';

/**
 * `NEXT_PUBLIC_API_URL` typically already includes the `/api` suffix, but
 * to be defensive we join carefully so we never double the prefix.
 */
function apiUrl(path: string): string {
  const base = BACKEND_URL.replace(/\/+$/, '');
  const suffix = path.startsWith('/') ? path : `/${path}`;
  if (base.endsWith('/api') && suffix.startsWith('/api/')) {
    return base + suffix.slice(4);
  }
  return base + suffix;
}

export default function QueryPage() {
  const qc = useQueryClient();
  const [question, setQuestion] = useState('');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const config = useQuery({
    queryKey: ['query-config'],
    queryFn: () => api.get('/query/config').then((r) => r.data),
  });
  const starters = useQuery<StarterPrompt[]>({
    queryKey: ['query-starters'],
    queryFn: () => api.get('/query/starters').then((r) => r.data),
  });
  const sessions = useQuery<ChatSession[]>({
    queryKey: ['chat-sessions'],
    queryFn: () => api.get('/query/sessions').then((r) => r.data),
    refetchInterval: false,
  });
  const messages = useQuery<ChatMessage[]>({
    queryKey: ['chat-messages', activeSessionId],
    queryFn: () =>
      activeSessionId
        ? api.get(`/query/sessions/${activeSessionId}/messages`).then((r) => r.data)
        : Promise.resolve([] as ChatMessage[]),
    enabled: !!activeSessionId,
  });

  const starterGroups = useMemo(() => {
    const groups: Record<string, StarterPrompt[]> = {};
    for (const item of starters.data || []) {
      groups[item.category] = [...(groups[item.category] || []), item];
    }
    return groups;
  }, [starters.data]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.data, streamingText, streaming]);

  const deleteSession = useMutation({
    mutationFn: (id: string) => api.delete(`/query/sessions/${id}`),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['chat-sessions'] });
      setActiveSessionId(null);
    },
  });

  function newChat() {
    setActiveSessionId(null);
    setStreamingText('');
    setQuestion('');
    setError(null);
  }

  async function send(text?: string) {
    const q = (text ?? question).trim();
    if (!q || streaming) return;
    setError(null);
    setStreamingText('');
    setStreaming(true);
    setQuestion('');

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const resp = await fetch(apiUrl('/api/query/ask'), {
        method: 'POST',
        signal: ctrl.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(typeof window !== 'undefined' && localStorage.getItem('access_token')
            ? { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
            : {}),
        },
        body: JSON.stringify({
          session_id: activeSessionId || undefined,
          question: q,
        }),
      });
      if (!resp.ok || !resp.body) {
        throw new Error(`HTTP ${resp.status}`);
      }

      // Optimistically show the user turn immediately
      if (activeSessionId) {
        qc.setQueryData<ChatMessage[]>(['chat-messages', activeSessionId], (prev) => [
          ...(prev || []),
          {
            id: `local-${Date.now()}`,
            session_id: activeSessionId,
            role: 'user',
            content: q,
            created_at: new Date().toISOString(),
          },
        ]);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      let assistantSoFar = '';
      let sessionIdFromStream: string | null = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx = buf.indexOf('\n\n');
        while (idx !== -1) {
          const raw = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          idx = buf.indexOf('\n\n');
          const lines = raw.split('\n');
          let ev = 'message';
          let data = '';
          for (const line of lines) {
            if (line.startsWith('event:')) ev = line.slice(6).trim();
            else if (line.startsWith('data:')) data += line.slice(5).trim();
          }
          if (!data) continue;
          try {
            const payload = JSON.parse(data);
            if (ev === 'session' && payload.session_id) {
              sessionIdFromStream = payload.session_id;
              if (!activeSessionId) {
                setActiveSessionId(payload.session_id);
              }
            } else if (ev === 'delta' && typeof payload.text === 'string') {
              assistantSoFar += payload.text;
              setStreamingText(assistantSoFar);
            } else if (ev === 'error') {
              throw new Error(payload.detail || 'stream error');
            }
          } catch {
            // ignore malformed event
          }
        }
      }

      // Stream complete — refresh the persisted view
      const finalSid = sessionIdFromStream || activeSessionId;
      if (finalSid) {
        await qc.invalidateQueries({ queryKey: ['chat-messages', finalSid] });
      }
      await qc.invalidateQueries({ queryKey: ['chat-sessions'] });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Stream failed';
      setError(msg);
    } finally {
      setStreaming(false);
      setStreamingText('');
      abortRef.current = null;
    }
  }

  const active = messages.data || [];
  const activeSession = (sessions.data || []).find((s) => s.id === activeSessionId);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Ask CA Copilot"
        subtitle={`Multi-turn command deck powered by ${config.data?.chat_model || 'Gemini'} · your firm's compliance signals in plain English.`}
      />

      <div className="grid gap-4 lg:grid-cols-[280px_1fr_300px]">
        {/* Sessions rail */}
        <aside className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <button
            onClick={newChat}
            className="mb-3 flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-violet-500 px-3 py-2 text-sm font-semibold text-slate-950 shadow-sm"
            data-testid="btn-new-chat"
          >
            <Plus className="h-4 w-4" /> New chat
          </button>
          <div className="px-1 pb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
            Sessions · {(sessions.data || []).length}
          </div>
          <div className="space-y-1">
            {(sessions.data || []).map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs ${
                  s.id === activeSessionId
                    ? 'bg-cyan-500/10 ring-1 ring-cyan-500/40'
                    : 'hover:bg-slate-900'
                }`}
              >
                <button
                  onClick={() => setActiveSessionId(s.id)}
                  className="flex flex-1 items-center gap-2 truncate text-left text-slate-200"
                  data-testid={`btn-session-${s.id}`}
                >
                  <MessageSquare className="h-3.5 w-3.5 shrink-0 text-slate-500" />
                  <span className="truncate">{s.title}</span>
                </button>
                <button
                  onClick={() => deleteSession.mutate(s.id)}
                  className="text-slate-500 opacity-0 transition group-hover:opacity-100 hover:text-rose-400"
                  title="Delete"
                  data-testid={`btn-del-session-${s.id}`}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
            {(sessions.data || []).length === 0 && (
              <div className="rounded-lg border border-dashed border-slate-800 px-3 py-4 text-center font-mono text-[10px] uppercase tracking-widest text-slate-600">
                No sessions yet
              </div>
            )}
          </div>
        </aside>

        {/* Conversation panel */}
        <div className="flex min-h-[560px] flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
          <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
            <div>
              <div className="font-mono text-[10px] uppercase tracking-widest text-cyan-400">
                {activeSession ? 'ACTIVE SESSION' : 'NEW CONVERSATION'}
              </div>
              <div className="mt-0.5 truncate text-sm font-semibold text-slate-100">
                {activeSession?.title || 'Start a new chat'}
              </div>
            </div>
            <div className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
              {config.data?.chat_model || 'gemini'} · {config.data?.provider || 'gemini'}
            </div>
          </div>

          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
            {active.length === 0 && !streaming && (
              <div className="mx-auto max-w-md pt-16 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-500/30 to-violet-500/30">
                  <Sparkles className="h-6 w-6 text-cyan-300" />
                </div>
                <h3 className="mt-3 text-lg font-semibold text-slate-100">
                  What would you like to know?
                </h3>
                <p className="mt-1 text-sm text-slate-400">
                  Pick a starter on the right, or type your compliance question below.
                </p>
              </div>
            )}
            {active.map((m) => (
              <MessageBubble key={m.id} role={m.role} content={m.content} />
            ))}
            {streaming && streamingText && (
              <MessageBubble role="assistant" content={streamingText} streaming />
            )}
            {streaming && !streamingText && (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="h-4 w-4 animate-spin" /> CA Copilot is thinking…
              </div>
            )}
            {error && (
              <div className="rounded-lg border border-rose-900 bg-rose-950/50 px-3 py-2 font-mono text-xs text-rose-300">
                {error}
              </div>
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="border-t border-slate-800 bg-slate-950/80 p-3"
          >
            <div className="flex items-end gap-2">
              <textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={2}
                disabled={streaming}
                className="flex-1 resize-none rounded-lg border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none placeholder:text-slate-600 focus:border-cyan-500/60"
                placeholder="Ask about GSTR-2B mismatches, deadlines, MSME exposure… (Shift+Enter for newline)"
                data-testid="input-question"
              />
              <button
                type="submit"
                disabled={!question.trim() || streaming}
                className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-cyan-500 to-violet-500 px-4 py-2 text-sm font-semibold text-slate-950 shadow-sm disabled:opacity-40"
                data-testid="btn-send"
              >
                {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                Send
              </button>
            </div>
          </form>
        </div>

        {/* Starters rail */}
        <aside className="rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="px-1 pb-2 font-mono text-[10px] uppercase tracking-widest text-slate-500">
            Starter Signals · {(starters.data || []).length}
          </div>
          <div className="space-y-3">
            {Object.entries(starterGroups).map(([category, items]) => (
              <div key={category}>
                <div className="px-1 pb-1 font-mono text-[10px] uppercase tracking-widest text-cyan-400">
                  {category}
                </div>
                <div className="space-y-1">
                  {items.map((item) => (
                    <button
                      key={item.intent}
                      onClick={() => send(item.prompt)}
                      disabled={streaming}
                      className={`block w-full rounded-lg border px-3 py-2 text-left text-xs leading-snug transition disabled:opacity-40 ${
                        item.recommended
                          ? 'border-cyan-800 bg-cyan-950/40 text-cyan-100 hover:bg-cyan-900/50'
                          : 'border-slate-800 bg-slate-900/60 text-slate-300 hover:bg-slate-900'
                      }`}
                      data-testid={`btn-starter-${item.intent}`}
                    >
                      {item.prompt}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
}

function MessageBubble({
  role,
  content,
  streaming = false,
}: {
  role: 'user' | 'assistant';
  content: string;
  streaming?: boolean;
}) {
  const isUser = role === 'user';
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-slate-950 ${
          isUser
            ? 'bg-gradient-to-br from-violet-400 to-fuchsia-400'
            : 'bg-gradient-to-br from-cyan-400 to-teal-400'
        }`}
      >
        {isUser ? <UserIcon className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
          isUser
            ? 'bg-violet-500/10 text-violet-50 ring-1 ring-violet-500/30'
            : 'bg-slate-900/70 text-slate-100 ring-1 ring-slate-800'
        }`}
      >
        <div className="whitespace-pre-wrap">{content}</div>
        {streaming && (
          <span className="ml-1 inline-block h-3 w-1.5 animate-pulse bg-cyan-400 align-middle" />
        )}
        {!isUser && !streaming && content.trim().length > 0 && (
          <div className="mt-2 flex items-center gap-1 border-t border-slate-800 pt-2">
            <SpeakButton text={content} surface="read_aloud" testId="btn-speak-assistant" />
            <span className="font-mono text-[10px] uppercase tracking-widest text-slate-500">
              Read aloud
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
