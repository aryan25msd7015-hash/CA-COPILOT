'use client';

import { useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import type { ColDef } from 'ag-grid-community';
import { api } from '@/lib/api';
import DataGrid from '@/components/shared/DataGrid';
import PageHeader from '@/components/shared/PageHeader';
import TaskStatusPoller from '@/components/shared/TaskStatusPoller';

interface QueryResult {
  sql: string;
  rows: Record<string, unknown>[];
  row_count: number;
  provider?: string;
  model?: string;
  question?: string;
  answer?: string;
}
interface SavedQuery { id: string; name: string; nl_query: string; run_count: number; last_run_at?: string; updated_at?: string; created_at?: string; }
interface StarterPrompt { category: string; intent: string; prompt: string; recommended: boolean; }
interface LlmCapability {
  llm_provider?: string;
  llm_model?: string;
  llm_tier?: string;
  fallback_reason?: string | null;
}

export default function QueryPage() {
  const [question, setQuestion] = useState('');
  const [taskId, setTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [savedSearch, setSavedSearch] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editQuery, setEditQuery] = useState('');
  const starters = useQuery<StarterPrompt[]>({ queryKey: ['query-starters'], queryFn: () => api.get('/query/starters').then(r => r.data) });
  const capability = useQuery<LlmCapability>({ queryKey: ['query-capability'], queryFn: () => api.get('/query/capability').then(r => r.data) });
  const saved = useQuery<SavedQuery[]>({ queryKey: ['saved-queries', savedSearch], queryFn: () => api.get('/query/saved', { params: savedSearch.trim() ? { q: savedSearch.trim() } : {} }).then(r => r.data) });
  const instant = useMutation({
    mutationFn: () => api.post('/query/ask-now', { question }),
    onSuccess: response => { setResult(response.data); setTaskId(null); },
  });
  const mutation = useMutation({ mutationFn: () => api.post('/query/ask', { question }), onSuccess: response => setTaskId(response.data.task_id) });
  const columnNames = result?.rows[0] ? Object.keys(result.rows[0]) : [];
  const columns: ColDef<Record<string, unknown>>[] = columnNames.map(name => ({
    colId: name,
    headerName: name,
    valueGetter: p => p.data?.[name],
    minWidth: 150,
  }));
  const starterGroups = useMemo(() => {
    const groups: Record<string, StarterPrompt[]> = {};
    for (const item of starters.data || []) {
      groups[item.category] = [...(groups[item.category] || []), item];
    }
    return groups;
  }, [starters.data]);

  async function save() {
    if (!question) return;
    await api.post('/query/saved', { name: question.slice(0, 60), nl_query: question });
    await saved.refetch();
  }

  async function remove(id: string) {
    await api.delete(`/query/saved/${id}`);
    await saved.refetch();
  }

  async function runSaved(id: string) {
    const response = await api.post(`/query/saved/${id}/run`);
    setResult(response.data);
    await saved.refetch();
  }

  function beginEdit(item: SavedQuery) {
    setEditingId(item.id);
    setEditName(item.name);
    setEditQuery(item.nl_query);
  }

  async function updateSaved(id: string) {
    await api.patch(`/query/saved/${id}`, { name: editName, nl_query: editQuery });
    setEditingId(null);
    await saved.refetch();
  }

  const activeProvider = capability.data?.llm_provider || 'deterministic_fallback';
  const activeModel = capability.data?.llm_model;
  const activeTier = capability.data?.llm_tier;

  return <div className="space-y-5">
    <PageHeader title="Natural Language Query" subtitle="Ask read-only questions across your firm's tenant-scoped data." />
    <div className="rounded-xl border bg-white p-3 text-xs text-gray-600">
      <span className="font-medium text-gray-800">LLM layer:</span>{' '}
      {activeProvider}
      {activeModel ? ` · ${activeModel}` : ''}
      {activeTier ? ` · ${activeTier} tier` : ''}
      {capability.data?.fallback_reason ? ` — ${capability.data.fallback_reason}` : ''}
      <span className="mt-1 block text-[11px] text-gray-400">
        Free tier: set GROQ_API_KEY (llama-3.1-8b-instant) or GEMINI_API_KEY (gemini-2.0-flash). Paid keys still take priority when present.
      </span>
    </div>
    <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
      <div className="space-y-3 rounded-xl border bg-white p-4">
        <textarea value={question} onChange={e => setQuestion(e.target.value)} rows={4} className="w-full rounded-lg border p-3 text-sm" placeholder="Which clients have deadlines due next week?" />
        <div className="flex flex-wrap items-center gap-2">
          <button disabled={!question || instant.isPending} onClick={() => instant.mutate()} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50">Run query</button>
          <button disabled={!question || mutation.isPending} onClick={() => mutation.mutate()} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">Run async</button>
          <button disabled={!question} onClick={save} className="rounded-lg border px-3 py-2 text-sm disabled:opacity-50">Save query</button>
          {instant.error && <span className="text-xs text-red-700">Query failed</span>}
          <TaskStatusPoller taskId={taskId} onSuccess={data => setResult(data as QueryResult)} />
        </div>
      </div>
      <div className="space-y-4 rounded-xl border bg-white p-4">
        <div><h2 className="text-sm font-medium">Starter prompts</h2><div className="mt-2 space-y-3">{Object.entries(starterGroups).map(([category, items]) => <div key={category}>
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-gray-500">{category}</p>
          <div className="space-y-1">{items.map(item => <button key={item.intent} onClick={() => setQuestion(item.prompt)} className={`block w-full rounded p-2 text-left text-xs hover:bg-blue-50 ${item.recommended ? 'bg-blue-50 text-blue-900' : 'bg-gray-50 text-gray-700'}`}>{item.prompt}</button>)}</div>
        </div>)}</div></div>
        <div><h2 className="text-sm font-medium">Saved queries</h2>
          <input value={savedSearch} onChange={event => setSavedSearch(event.target.value)} placeholder="Search saved" className="mt-2 w-full rounded border px-2 py-1 text-xs" />
          <div className="mt-2 space-y-2">{(saved.data || []).map(item => <div key={item.id} className="rounded bg-gray-50 p-2">
            {editingId === item.id ? <div className="space-y-2">
              <input value={editName} onChange={event => setEditName(event.target.value)} className="w-full rounded border px-2 py-1 text-xs" />
              <textarea value={editQuery} onChange={event => setEditQuery(event.target.value)} rows={3} className="w-full rounded border px-2 py-1 text-xs" />
              <div className="flex gap-2"><button onClick={() => updateSaved(item.id)} className="text-xs text-blue-700">Save</button><button onClick={() => setEditingId(null)} className="text-xs text-gray-600">Cancel</button></div>
            </div> : <div className="space-y-1">
              <button onClick={() => setQuestion(item.nl_query)} className="block w-full text-left text-xs font-medium">{item.name}</button>
              <p className="line-clamp-2 text-xs text-gray-500">{item.nl_query}</p>
              <p className="text-[11px] text-gray-400">Runs: {item.run_count || 0}{item.last_run_at ? ` | Last: ${new Date(item.last_run_at).toLocaleDateString('en-IN')}` : ''}</p>
              <div className="flex gap-2"><button onClick={() => runSaved(item.id)} className="text-xs text-blue-700">Run</button><button onClick={() => beginEdit(item)} className="text-xs text-gray-700">Edit</button><button onClick={() => remove(item.id)} className="text-xs text-red-600">Delete</button></div>
            </div>}
          </div>)}</div>
        </div>
      </div>
    </div>
    {result && <div className="space-y-3 rounded-xl border bg-white p-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500">
        <span>{result.row_count} rows</span>
        <span>Provider: {result.provider || 'unknown'}</span>
        {result.model && <span>Model: {result.model}</span>}
        {result.question && <span>Question: {result.question}</span>}
      </div>
      {result.answer && <p className="whitespace-pre-wrap rounded-lg bg-blue-50 p-3 text-sm text-blue-950">{result.answer}</p>}
      <details><summary className="cursor-pointer text-sm font-medium text-blue-700">Generated SQL</summary><pre className="mt-2 overflow-auto rounded bg-gray-900 p-3 text-xs text-gray-100">{result.sql}</pre></details>
      <DataGrid rows={result.rows} columns={columns} />
    </div>}
  </div>;
}
