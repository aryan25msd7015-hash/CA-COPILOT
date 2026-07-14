'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import {
  Activity, Bot, BrainCircuit, ChevronDown, Gauge, Mic, MicOff,
  Navigation, Radar, Send, ShieldCheck, Sparkles, Volume2, X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { navItemsForRole } from '@/lib/navigation';
import { useAuth } from '@/hooks/useAuth';
import { useTts } from '@/lib/useTts';
import type { Client } from '@/types';

type Message = {
  role: 'assistant' | 'user' | 'system';
  text: string;
};

type Telemetry = {
  clients: number;
  highRisk: number;
  deadlines: number;
  exceptions: number;
  agentStatus: string;
  agentCount: number;
};

type OrgReadiness = {
  agent_readiness?: {
    status?: string;
    enabled_agents?: string[];
  } | null;
};

type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onresult: ((event: { results: ArrayLike<{ 0: { transcript: string }; isFinal: boolean }> }) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
  start: () => void;
  stop: () => void;
};

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

const QUICK_ACTIONS = [
  { label: 'Risk scan', command: 'show high risk clients', Icon: Radar },
  { label: 'Today brief', command: 'what needs attention today', Icon: Activity },
  { label: 'Autopilot', command: 'open autopilot exceptions', Icon: BrainCircuit },
  { label: 'New task', command: 'create task: Review GST reconciliation', Icon: ShieldCheck },
];

const WAKE_PROMPTS = [
  'Friday, open deadlines',
  'Friday, summarize today',
  'Friday, show high risk clients',
  'Friday, ask CA Copilot GST mismatch exposure',
];

const WAKE_WORD_RE = /^(hey\s+)?(ca\s+)?friday[\s,.:;-]*/i;

function normalize(value: string) {
  return value.trim().toLowerCase();
}

function pickTaskTitle(command: string) {
  return command
    .replace(/^create (a )?task( to|:)?/i, '')
    .replace(/^add (a )?task( to|:)?/i, '')
    .trim() || 'CA-FRIDAY follow-up';
}

function formatPath(pathname: string) {
  if (pathname === '/') return 'Command Center';
  return pathname.replace('/', '').replace(/-/g, ' ') || 'Workspace';
}

function commandAfterWakeWord(transcript: string) {
  const normalized = transcript.trim();
  if (!WAKE_WORD_RE.test(normalized)) return null;
  return normalized.replace(WAKE_WORD_RE, '').trim();
}

export default function VoiceAssistant() {
  const { user } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const alwaysListenRef = useRef(false);
  const restartingRef = useRef(false);
  const manuallyStoppedRef = useRef(false);
  const listenDeadlineRef = useRef(0);
  const [open, setOpen] = useState(false);
  const [listening, setListening] = useState(false);
  const [alwaysListening, setAlwaysListening] = useState(false);
  const [voiceNotice, setVoiceNotice] = useState('Wake word: "Friday"');
  const [lastHeard, setLastHeard] = useState('');
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [telemetry, setTelemetry] = useState<Telemetry>({
    clients: 0,
    highRisk: 0,
    deadlines: 0,
    exceptions: 0,
    agentStatus: 'unknown',
    agentCount: 0,
  });
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'system',
      text: 'CA-FRIDAY online. Practice telemetry linked. Say "Friday" before a command and I will respond.',
    },
    {
      role: 'assistant',
      text: 'Good to go. Ask me to open a module, scan high-risk clients, brief today, create a task, or ask CA Copilot a technical question.',
    },
  ]);

  const navItems = useMemo(() => navItemsForRole(user?.role), [user?.role]);
  const tts = useTts({ surface: 'friday' });

  function addMessage(message: Message) {
    setMessages(current => [...current.slice(-8), message]);
  }

  function speak(text: string) {
    if (!voiceEnabled) return;
    // Try ElevenLabs; fall back to browser speechSynthesis if it errors.
    tts.speak(text).catch(() => {
      if (typeof window === 'undefined' || !window.speechSynthesis) return;
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1;
      utterance.pitch = 0.94;
      window.speechSynthesis.speak(utterance);
    });
  }

  function answer(text: string) {
    addMessage({ role: 'assistant', text });
    speak(text);
  }

  function findNavigation(command: string) {
    const needle = normalize(command)
      .replace(/^friday,? /, '')
      .replace(/^ca friday,? /, '')
      .replace(/^open /, '')
      .replace(/^go to /, '')
      .replace(/^show /, '')
      .replace(/^take me to /, '');
    return navItems.find(item =>
      normalize([item.label, item.group, item.href, ...(item.keywords || [])].join(' ')).includes(needle)
      || needle.includes(normalize(item.label))
      || (item.keywords || []).some(keyword => needle.includes(normalize(keyword))),
    );
  }

  const loadTelemetry = useCallback(async () => {
    const [clientsRes, deadlinesRes, autopilotRes, readinessRes] = await Promise.allSettled([
      api.get<Client[]>('/clients?limit=2000'),
      api.get('/deadlines?limit=2000'),
      api.get('/autopilot/overview?auto_refresh=false'),
      api.get<OrgReadiness>('/organizations/me/readiness'),
    ]);
    const clients = clientsRes.status === 'fulfilled' ? clientsRes.value.data : [];
    const deadlines = deadlinesRes.status === 'fulfilled' ? deadlinesRes.value.data : [];
    const autopilot = autopilotRes.status === 'fulfilled' ? autopilotRes.value.data : null;
    const readiness = readinessRes.status === 'fulfilled' ? readinessRes.value.data.agent_readiness : null;
    return {
      clients: clients.length,
      highRisk: clients.filter(client => client.health_score < 50).length,
      deadlines: deadlines.length,
      exceptions: autopilot?.summary?.open_count ?? 0,
      agentStatus: readiness?.status || 'unknown',
      agentCount: readiness?.enabled_agents?.length || 0,
    };
  }, []);

  const refreshTelemetry = useCallback(async () => {
    setTelemetry(await loadTelemetry());
  }, [loadTelemetry]);

  useEffect(() => {
    if (!user) return;
    refreshTelemetry();
    return () => {
      alwaysListenRef.current = false;
      recognitionRef.current?.stop();
      window.speechSynthesis?.cancel();
      tts.stop();
    };
  }, [refreshTelemetry, user]);

  async function summarizePractice() {
    const fresh = await loadTelemetry();
    setTelemetry(fresh);
    return `Briefing ready. ${fresh.clients} clients are in scope, ${fresh.highRisk} are high risk, ${fresh.deadlines} deadlines are visible, and ${fresh.exceptions} autopilot exceptions need review. Agent readiness is ${fresh.agentStatus} with ${fresh.agentCount} agents enabled.`;
  }

  async function showHighRiskClients() {
    const response = await api.get<Client[]>('/clients?limit=2000');
    const highRisk = response.data
      .filter(client => client.health_score < 50)
      .sort((a, b) => a.health_score - b.health_score)
      .slice(0, 5);
    router.push('/clients');
    if (!highRisk.length) return 'Risk scan complete. No high-risk clients found. I opened the client deck.';
    return `Risk scan complete. I opened clients. Priority list: ${highRisk.map(client => `${client.name}, score ${client.health_score}`).join('; ')}.`;
  }

  async function createTask(command: string) {
    const title = pickTaskTitle(command);
    await api.post('/work/tasks', { title, priority: 'medium' });
    router.push('/work');
    return `Task logged: ${title}. Routing you to Work and Daybook.`;
  }

  async function askCopilot(command: string) {
    const question = command.replace(/^ask( ca copilot)?/i, '').trim() || command;
    const response = await api.post('/query/ask', { question });
    router.push('/query');
    return `CA query launched. Task ID ${response.data.task_id}. Query workspace is open.`;
  }

  async function runCommand(rawCommand: string) {
    const command = rawCommand.trim();
    if (!command || busy) return;
    setInput('');
    setBusy(true);
    addMessage({ role: 'user', text: command });

    try {
      const lower = normalize(command).replace(/^friday,? /, '').replace(/^ca friday,? /, '');
      const nav = findNavigation(command);

      if (nav && /^(friday,? |ca friday,? )?(open|go to|show|take me to)/i.test(command)) {
        router.push(nav.href);
        answer(`Route plotted. Opening ${nav.label}.`);
        return;
      }

      if (lower.includes('high risk') || lower.includes('risky client') || lower.includes('risk scan')) {
        answer(await showHighRiskClients());
        return;
      }

      if (lower.includes('today') || lower.includes('attention') || lower.includes('summary') || lower.includes('brief') || lower.includes('overview')) {
        answer(await summarizePractice());
        return;
      }

      if (/^(create|add) (a )?task/i.test(lower)) {
        answer(await createTask(command));
        return;
      }

      if (/^ask/i.test(lower) || lower.includes('question')) {
        answer(await askCopilot(command));
        return;
      }

      if (nav) {
        router.push(nav.href);
        answer(`I found ${nav.label}. Moving there now.`);
        return;
      }

      // Fallback: hand off to Gemini via /api/query/friday
      try {
        const fresh = await loadTelemetry();
        const context = `Clients: ${fresh.clients} · High-risk: ${fresh.highRisk} · Deadlines visible: ${fresh.deadlines} · Autopilot exceptions: ${fresh.exceptions} · Agent status: ${fresh.agentStatus} (${fresh.agentCount} agents).`;
        const resp = await api.post<{ answer: string }>('/query/friday', { question: command, context });
        answer(resp.data.answer || 'Signal received, no output.');
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Friday link degraded';
        answer(`Mission interrupted: ${msg}`);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Unknown failure';
      answer(`Mission interrupted: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  function shouldRestartRecognition(alwaysOn: boolean) {
    if (manuallyStoppedRef.current) return false;
    if (alwaysOn || alwaysListenRef.current) return true;
    return Date.now() < listenDeadlineRef.current;
  }

  function startRecognition(alwaysOn = false) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) {
      setOpen(true);
      setAlwaysListening(false);
      alwaysListenRef.current = false;
      setVoiceNotice('Manual command channel active');
      answer('Voice recognition is not available in this browser. Manual command channel is active.');
      return;
    }

    manuallyStoppedRef.current = false;
    if (!alwaysOn) {
      listenDeadlineRef.current = Date.now() + 30000;
    }
    recognitionRef.current?.stop();
    const recognition = new Recognition();
    recognition.continuous = alwaysOn;
    recognition.interimResults = false;
    recognition.lang = 'en-IN';
    recognition.onstart = () => {
      setListening(true);
      setVoiceNotice(alwaysOn ? 'Listening. Say "Friday" before a command.' : 'Listening for this command.');
    };
    recognition.onresult = event => {
      const transcript = event.results[event.results.length - 1]?.[0]?.transcript || '';
      if (!transcript) return;
      setLastHeard(transcript);

      if (alwaysListenRef.current) {
        const command = commandAfterWakeWord(transcript);
        if (command === null) {
          setVoiceNotice('Background audio ignored. Waiting for "Friday".');
          return;
        }
        setOpen(true);
        if (!command) {
          answer('Yes. I am listening.');
          return;
        }
        runCommand(command);
        return;
      }

      runCommand(transcript);
    };
    recognition.onerror = event => {
      const code = event.error || 'unknown';
      setListening(false);
      if (code === 'no-speech' || code === 'aborted') {
        setVoiceNotice(alwaysListenRef.current ? 'Still standing by for "Friday".' : 'No speech yet. Listening window remains open.');
        return;
      }
      if (code === 'not-allowed' || code === 'service-not-allowed') {
        alwaysListenRef.current = false;
        setAlwaysListening(false);
        setVoiceNotice('Microphone permission is blocked');
        answer('Microphone permission is blocked. Allow microphone access in the browser to enable always-listening mode.');
        return;
      }
      if (code === 'network') {
        setVoiceNotice('Speech service unavailable. Type the command for now.');
        return;
      }
      setVoiceNotice(`Voice recognizer paused: ${code}`);
    };
    recognition.onend = () => {
      setListening(false);
      recognitionRef.current = null;
      if (!shouldRestartRecognition(alwaysOn)) {
        if (!alwaysListenRef.current) setVoiceNotice('Voice idle');
        return;
      }
      window.setTimeout(() => {
        if (!shouldRestartRecognition(alwaysOn) || restartingRef.current) return;
        restartingRef.current = true;
        startRecognition(alwaysOn);
        restartingRef.current = false;
      }, 120);
    };
    recognitionRef.current = recognition;
    setOpen(true);
    setVoiceNotice(alwaysOn ? 'Always listening. Say "Friday" to activate.' : 'Listening for this command.');
    try {
      recognition.start();
    } catch {
      setListening(false);
      setVoiceNotice('Voice recognizer is already starting');
    }
  }

  function toggleAlwaysListening() {
    if (alwaysListenRef.current) {
      alwaysListenRef.current = false;
      manuallyStoppedRef.current = true;
      listenDeadlineRef.current = 0;
      setAlwaysListening(false);
      setListening(false);
      setVoiceNotice('Always-listening mode off');
      recognitionRef.current?.stop();
      return;
    }
    alwaysListenRef.current = true;
    setAlwaysListening(true);
    startRecognition(true);
  }

  function toggleSingleCommandListening() {
    if (listening && !alwaysListening) {
      manuallyStoppedRef.current = true;
      listenDeadlineRef.current = 0;
      recognitionRef.current?.stop();
      setListening(false);
      setVoiceNotice('Voice idle');
      return;
    }
    alwaysListenRef.current = false;
    setAlwaysListening(false);
    startRecognition(false);
  }

  if (!user) return null;

  return (
    <div className="fixed bottom-5 right-5 z-40 flex max-w-[calc(100vw-2rem)] flex-col items-end gap-3">
      {open && (
        <section className="jarvis-panel motion-pop w-[min(520px,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-cyan-200/40 bg-slate-950/92 text-white shadow-[0_28px_90px_rgba(8,47,73,0.42)] backdrop-blur-2xl">
          <div className="relative overflow-hidden border-b border-cyan-300/20 px-4 py-4">
            <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(34,211,238,0.14),transparent_40%,rgba(59,130,246,0.12))]" />
            <div className="relative flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className={`jarvis-core grid h-12 w-12 place-items-center rounded-2xl ${listening ? 'is-listening' : ''}`}>
                  <Bot className="h-5 w-5 text-cyan-100" />
                </span>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.26em] text-cyan-200">CA-FRIDAY</p>
                  <h2 className="text-base font-semibold text-white">Agentic practice assistant</h2>
                  <p className="text-xs text-cyan-100/70">{alwaysListening ? voiceNotice : listening ? 'Audio channel live' : `Standing by on ${formatPath(pathname)}`}</p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  title={voiceEnabled ? 'Mute spoken replies' : 'Enable spoken replies'}
                  onClick={() => setVoiceEnabled(value => !value)}
                  className={`grid h-9 w-9 place-items-center rounded-xl border border-white/10 transition hover:bg-white/10 ${voiceEnabled ? 'text-cyan-200' : 'text-slate-500'}`}
                >
                  <Volume2 className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  title="Close CA-FRIDAY"
                  onClick={() => setOpen(false)}
                  className="grid h-9 w-9 place-items-center rounded-xl border border-white/10 text-slate-300 transition hover:bg-white/10 hover:text-white"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>

          <div className="grid gap-3 border-b border-cyan-300/20 p-4 sm:grid-cols-4">
            {[
              { label: 'Clients', value: telemetry.clients, tone: 'text-cyan-200' },
              { label: 'Risk', value: telemetry.highRisk, tone: 'text-rose-200' },
              { label: 'Deadlines', value: telemetry.deadlines, tone: 'text-amber-200' },
              { label: 'Agents', value: telemetry.agentCount, tone: telemetry.agentStatus === 'ready' ? 'text-emerald-200' : 'text-amber-200' },
            ].map(item => (
              <div key={item.label} className="rounded-xl border border-white/10 bg-white/[0.06] px-3 py-2">
                <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">{item.label}</p>
                <p className={`mt-1 text-lg font-semibold ${item.tone}`}>{item.value}</p>
              </div>
            ))}
          </div>

          <div className="border-b border-cyan-300/20 px-4 py-3">
            <button
              type="button"
              onClick={toggleAlwaysListening}
              className={`flex w-full items-center justify-between rounded-2xl border px-3 py-2 text-left transition ${
                alwaysListening
                  ? 'border-emerald-300/40 bg-emerald-300/10 text-emerald-100'
                  : 'border-white/10 bg-white/[0.05] text-slate-200 hover:border-cyan-200/40 hover:bg-cyan-300/10'
              }`}
            >
              <span>
                <span className="block text-xs font-semibold uppercase tracking-[0.18em]">Always-listening wake mode</span>
                <span className="text-xs text-slate-400">
                  {alwaysListening ? 'Active. Background speech is ignored until you say "Friday".' : 'Enable once, then say "Friday" before commands.'}
                </span>
                <span className="mt-1 block text-xs text-cyan-100/70">{voiceNotice}</span>
                {lastHeard && (
                  <span className="mt-1 block truncate text-[11px] text-slate-500">
                    Last heard: {lastHeard}
                  </span>
                )}
              </span>
              <span className={`grid h-9 w-9 place-items-center rounded-xl ${alwaysListening ? 'bg-emerald-400 text-slate-950' : 'bg-slate-900 text-cyan-200'}`}>
                {alwaysListening ? <Mic className="h-4 w-4" /> : <MicOff className="h-4 w-4" />}
              </span>
            </button>
          </div>

          <div className="grid gap-4 p-4 lg:grid-cols-[1fr_.78fr]">
            <div className="min-h-0">
              <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
                <Activity className="h-3.5 w-3.5" />
                Mission log
              </div>
              <div className="max-h-72 space-y-3 overflow-y-auto pr-1">
                {messages.map((message, index) => (
                  <div key={`${message.role}-${index}`} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                    <p className={`max-w-[88%] rounded-2xl px-3 py-2 text-sm leading-5 ${
                      message.role === 'user'
                        ? 'bg-cyan-300 text-slate-950'
                        : message.role === 'system'
                          ? 'border border-cyan-300/20 bg-cyan-300/10 text-cyan-100'
                          : 'border border-white/10 bg-white/[0.07] text-slate-100'
                    }`}>
                      {message.text}
                    </p>
                  </div>
                ))}
              </div>
            </div>

            <aside className="space-y-3">
              <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-3">
                <div className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-100">
                  <Gauge className="h-3.5 w-3.5" />
                  Command rail
                </div>
                <div className="grid gap-2">
                  {QUICK_ACTIONS.map(({ label, command, Icon }) => (
                    <button
                      key={command}
                      type="button"
                      onClick={() => runCommand(command)}
                      className="group flex items-center gap-2 rounded-xl border border-white/10 bg-slate-950/40 px-3 py-2 text-left text-xs font-semibold text-slate-200 transition hover:border-cyan-200/50 hover:bg-cyan-300/10 hover:text-white"
                    >
                      <Icon className="h-4 w-4 text-cyan-200" />
                      <span>{label}</span>
                      <Navigation className="ml-auto h-3.5 w-3.5 text-slate-500 transition group-hover:text-cyan-200" />
                    </button>
                  ))}
                </div>
              </div>
              <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-3">
                <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Try saying</p>
                <div className="space-y-1.5">
                  {WAKE_PROMPTS.map(prompt => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setInput(prompt)}
                      className="block w-full truncate rounded-lg px-2 py-1.5 text-left text-xs text-slate-300 transition hover:bg-white/10 hover:text-white"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            </aside>
          </div>

          <div className="border-t border-cyan-300/20 p-4">
            <form
              className="flex items-center gap-2"
              onSubmit={event => {
                event.preventDefault();
                runCommand(input);
              }}
            >
              <div className="relative min-w-0 flex-1">
                <input
                  value={input}
                  onChange={event => setInput(event.target.value)}
                placeholder={alwaysListening ? 'Or type without wake word...' : 'Command CA-FRIDAY...'}
                  className="h-11 w-full rounded-2xl border border-cyan-300/20 bg-slate-900/80 px-4 pr-12 text-sm text-white outline-none transition placeholder:text-slate-500 focus:border-cyan-200 focus:ring-4 focus:ring-cyan-300/10"
                />
                <Sparkles className="absolute right-4 top-3.5 h-4 w-4 text-cyan-200/70" />
              </div>
              <button
                type="button"
                title={alwaysListening ? 'Disable always listening' : listening ? 'Stop listening' : 'Start one voice command'}
                onClick={alwaysListening ? toggleAlwaysListening : toggleSingleCommandListening}
                className={`grid h-11 w-11 place-items-center rounded-2xl text-white shadow-lg transition ${listening ? 'bg-rose-600 shadow-rose-950/30' : 'bg-cyan-500 shadow-cyan-950/30 hover:bg-cyan-400'}`}
              >
                {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </button>
              <button
                type="submit"
                title="Run command"
                disabled={busy}
                className="grid h-11 w-11 place-items-center rounded-2xl bg-white text-slate-950 shadow-lg transition hover:bg-cyan-50 disabled:opacity-50"
              >
                {busy ? <Sparkles className="h-4 w-4 animate-pulse" /> : <Send className="h-4 w-4" />}
              </button>
            </form>
          </div>
        </section>
      )}

      <button
        type="button"
        aria-label="Voice Agent"
        data-testid="voice-agent-launcher"
        onClick={() => {
          setOpen(true);
          if (!alwaysListenRef.current) toggleAlwaysListening();
        }}
        className="jarvis-launcher group relative flex h-16 items-center gap-3 overflow-hidden rounded-2xl border border-cyan-200/50 bg-slate-950 px-4 text-white shadow-[0_18px_45px_rgba(8,47,73,0.38)] transition hover:-translate-y-0.5"
      >
        <span className="jarvis-orb relative grid h-10 w-10 place-items-center rounded-2xl">
          {alwaysListening || listening ? <Mic className="h-4 w-4 text-white" /> : <Sparkles className="h-4 w-4 text-white" />}
          {(alwaysListening || listening) && <span className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.9)]" />}
        </span>
        <span className="hidden min-w-0 sm:block">
          <span className="block text-left text-[10px] font-semibold uppercase tracking-[0.24em] text-cyan-200">CA-FRIDAY</span>
          <span className="block text-left text-sm font-semibold">{busy ? 'Executing' : alwaysListening ? 'Wake mode' : listening ? 'Listening' : 'Standing by'}</span>
        </span>
        {busy ? <Sparkles className="h-4 w-4 animate-pulse text-cyan-200" /> : open ? <ChevronDown className="h-4 w-4 text-cyan-200" /> : <Navigation className="h-4 w-4 text-cyan-200" />}
      </button>
    </div>
  );
}
