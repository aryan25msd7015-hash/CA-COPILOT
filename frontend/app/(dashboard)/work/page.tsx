'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Client, User } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import StatusBadge from '@/components/shared/StatusBadge';

interface WorkOverview {
  open_tasks: number;
  overdue_tasks: number;
  due_today: number;
  due_next_7_days: number;
  blocked_tasks: number;
  unassigned_tasks: number;
  review_queue: number;
  today_daybook: number;
  daybook_closed_today: number;
  by_priority: Record<string, number>;
  by_status: Record<string, number>;
  by_stage: Record<string, number>;
}

interface PracticeTask {
  id: string;
  client_name: string;
  title: string;
  service_type: string;
  priority: string;
  status: string;
  stage: string;
  due_date?: string;
  assigned_to_email?: string;
  reviewer_email?: string;
  checklist_progress: number;
  checklist_done: number;
  checklist_total: number;
  days_until_due?: number;
  is_overdue: boolean;
  tags: string[];
}

interface DaybookEntry {
  id: string;
  client_name: string;
  activity_type: string;
  summary: string;
  assigned_to_email?: string;
  status: string;
  created_at?: string;
}

const today = new Date().toISOString().slice(0, 10);
const nextWeek = new Date(Date.now() + 7 * 86400000).toISOString().slice(0, 10);

export default function WorkPage() {
  const [taskFilters, setTaskFilters] = useState({ status: 'open,in_progress,review,blocked', client_id: '', priority: '', assigned_to: '', due_to: nextWeek });
  const [daybookFilters, setDaybookFilters] = useState({ target_date: today, client_id: '', status: '', activity_type: '' });
  const [taskForm, setTaskForm] = useState({
    client_id: '',
    title: '',
    service_type: 'compliance',
    priority: 'medium',
    due_date: today,
    assigned_to: '',
    reviewer_id: '',
  });
  const [daybookForm, setDaybookForm] = useState({
    client_id: '',
    entry_date: today,
    activity_type: 'follow_up',
    summary: '',
    assigned_to: '',
  });

  const overview = useQuery<WorkOverview>({ queryKey: ['work-overview'], queryFn: () => api.get('/work/overview').then(r => r.data) });
  const tasks = useQuery<PracticeTask[]>({
    queryKey: ['work-tasks', taskFilters],
    queryFn: () => api.get('/work/tasks', {
      params: {
        ...taskFilters,
        client_id: taskFilters.client_id || undefined,
        priority: taskFilters.priority || undefined,
        assigned_to: taskFilters.assigned_to || undefined,
        due_to: taskFilters.due_to || undefined,
      },
    }).then(r => r.data),
  });
  const daybook = useQuery<DaybookEntry[]>({
    queryKey: ['daybook', daybookFilters],
    queryFn: () => api.get('/work/daybook', {
      params: {
        ...daybookFilters,
        client_id: daybookFilters.client_id || undefined,
        status: daybookFilters.status || undefined,
        activity_type: daybookFilters.activity_type || undefined,
      },
    }).then(r => r.data),
  });
  const clients = useQuery<Client[]>({ queryKey: ['clients'], queryFn: () => api.get('/clients').then(r => r.data) });
  const users = useQuery<User[]>({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data).catch(() => []) });

  const board = useMemo(() => {
    const groups: Record<string, PracticeTask[]> = { open: [], in_progress: [], review: [], blocked: [], done: [] };
    for (const task of tasks.data || []) {
      (groups[task.status] ||= []).push(task);
    }
    return groups;
  }, [tasks.data]);

  async function createTask(event: FormEvent) {
    event.preventDefault();
    await api.post('/work/tasks', {
      ...taskForm,
      client_id: taskForm.client_id || null,
      assigned_to: taskForm.assigned_to || null,
      reviewer_id: taskForm.reviewer_id || null,
      checklist: [
        { label: 'Data received', done: false },
        { label: 'Maker completed', done: false },
        { label: 'Reviewer signed off', done: false },
      ],
    });
    setTaskForm({ ...taskForm, title: '' });
    await Promise.all([tasks.refetch(), overview.refetch()]);
  }

  async function createDaybook(event: FormEvent) {
    event.preventDefault();
    await api.post('/work/daybook', {
      ...daybookForm,
      client_id: daybookForm.client_id || null,
      assigned_to: daybookForm.assigned_to || null,
    });
    setDaybookForm({ ...daybookForm, summary: '' });
    await Promise.all([daybook.refetch(), overview.refetch()]);
  }

  async function updateTask(task: PracticeTask, status: string, stage = task.stage) {
    await api.patch(`/work/tasks/${task.id}`, { status, stage });
    await Promise.all([tasks.refetch(), overview.refetch()]);
  }

  const metrics = [
    ['Open', overview.data?.open_tasks || 0],
    ['Overdue', overview.data?.overdue_tasks || 0],
    ['Due today', overview.data?.due_today || 0],
    ['Due 7 days', overview.data?.due_next_7_days || 0],
    ['Review', overview.data?.review_queue || 0],
    ['Blocked', overview.data?.blocked_tasks || 0],
    ['Unassigned', overview.data?.unassigned_tasks || 0],
    ['Daybook', `${overview.data?.daybook_closed_today || 0}/${overview.data?.today_daybook || 0}`],
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold text-slate-950">Work & Daybook</h1>
        <p className="text-sm text-slate-500">Daily practice command center for ownership, maker-checker movement, follow-ups, and bottlenecks.</p>
      </div>

      <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg border border-slate-200 bg-white p-4">
            <p className="text-xs text-slate-500">{label}</p>
            <p className="mt-1 text-xl font-semibold text-slate-950">{value}</p>
          </div>
        ))}
      </div>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Work overview</h2>
            <p className="mt-1 text-xs text-slate-500">Filter active jobs by client, owner, priority, and due window.</p>
          </div>
          <StatusBadge value={tasks.isLoading ? 'pending' : `${tasks.data?.length || 0} tasks`} />
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-5">
          <select value={taskFilters.status} onChange={e => setTaskFilters({ ...taskFilters, status: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
            <option value="open,in_progress,review,blocked">Active</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="review">Review</option>
            <option value="blocked">Blocked</option>
            <option value="done">Done</option>
            <option value="">All</option>
          </select>
          <ClientSelect clients={clients.data || []} value={taskFilters.client_id} onChange={value => setTaskFilters({ ...taskFilters, client_id: value })} />
          <select value={taskFilters.priority} onChange={e => setTaskFilters({ ...taskFilters, priority: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
            <option value="">All priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select value={taskFilters.assigned_to} onChange={e => setTaskFilters({ ...taskFilters, assigned_to: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
            <option value="">All owners</option>
            {(users.data || []).map(user => <option key={user.id} value={user.id}>{user.email}</option>)}
          </select>
          <input type="date" value={taskFilters.due_to} onChange={e => setTaskFilters({ ...taskFilters, due_to: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" />
        </div>
        <div className="mt-4 grid gap-3 xl:grid-cols-4">
          {['open', 'in_progress', 'review', 'blocked'].map(status => (
            <div key={status} className="rounded-lg border border-slate-200">
              <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{status.replace('_', ' ')}</h3>
                <span className="text-xs text-slate-500">{board[status]?.length || 0}</span>
              </div>
              <div className="space-y-2 p-3">
                {(board[status] || []).map(task => (
                  <div key={task.id} className={`rounded-lg border p-3 ${task.is_overdue ? 'border-red-200 bg-red-50' : 'border-slate-200 bg-white'}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{task.title}</p>
                        <p className="mt-1 text-xs text-slate-500">{task.client_name || 'General'} / {task.service_type}</p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{task.priority}</span>
                    </div>
                    <div className="mt-3 h-2 rounded-full bg-slate-100">
                      <div className="h-2 rounded-full bg-blue-600" style={{ width: `${task.checklist_progress || 0}%` }} />
                    </div>
                    <p className="mt-2 text-xs text-slate-500">{task.checklist_done}/{task.checklist_total} checklist / Due {task.due_date || '-'}</p>
                    <p className="mt-1 text-xs text-slate-500">Owner: {task.assigned_to_email || 'Unassigned'}</p>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {task.status !== 'in_progress' && <button onClick={() => updateTask(task, 'in_progress', 'maker')} className="rounded-md border px-2 py-1 text-xs">Start</button>}
                      {task.status !== 'review' && <button onClick={() => updateTask(task, 'review', 'review')} className="rounded-md border px-2 py-1 text-xs">Review</button>}
                      {task.status !== 'blocked' && <button onClick={() => updateTask(task, 'blocked')} className="rounded-md border px-2 py-1 text-xs">Block</button>}
                      <button onClick={() => updateTask(task, 'done', 'closed')} className="rounded-md bg-slate-950 px-2 py-1 text-xs text-white">Close</button>
                    </div>
                  </div>
                ))}
                {!board[status]?.length && <p className="py-6 text-center text-xs text-slate-500">No tasks</p>}
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[.8fr_1.2fr]">
        <section className="space-y-4">
          <form onSubmit={createTask} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Create task</h2>
            <div className="mt-3 space-y-3">
              <input required value={taskForm.title} onChange={e => setTaskForm({ ...taskForm, title: e.target.value })} placeholder="Task title" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <ClientSelect clients={clients.data || []} value={taskForm.client_id} onChange={value => setTaskForm({ ...taskForm, client_id: value })} />
              <div className="grid grid-cols-2 gap-2">
                <select value={taskForm.service_type} onChange={e => setTaskForm({ ...taskForm, service_type: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
                  <option value="compliance">Compliance</option>
                  <option value="gst">GST</option>
                  <option value="audit">Audit</option>
                  <option value="billing">Billing</option>
                </select>
                <select value={taskForm.priority} onChange={e => setTaskForm({ ...taskForm, priority: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm">
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
              </div>
              <input type="date" value={taskForm.due_date} onChange={e => setTaskForm({ ...taskForm, due_date: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <select value={taskForm.assigned_to} onChange={e => setTaskForm({ ...taskForm, assigned_to: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
                <option value="">Assign later</option>
                {(users.data || []).map(user => <option key={user.id} value={user.id}>{user.email}</option>)}
              </select>
              <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Create task</button>
            </div>
          </form>

          <form onSubmit={createDaybook} className="rounded-lg border border-slate-200 bg-white p-4">
            <h2 className="text-sm font-semibold text-slate-900">Add daybook entry</h2>
            <div className="mt-3 space-y-3">
              <ClientSelect clients={clients.data || []} value={daybookForm.client_id} onChange={value => setDaybookForm({ ...daybookForm, client_id: value })} />
              <input type="date" value={daybookForm.entry_date} onChange={e => setDaybookForm({ ...daybookForm, entry_date: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <select value={daybookForm.activity_type} onChange={e => setDaybookForm({ ...daybookForm, activity_type: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
                <option value="follow_up">Follow-up</option>
                <option value="client_call">Client call</option>
                <option value="internal_review">Internal review</option>
                <option value="filing">Filing</option>
              </select>
              <textarea required value={daybookForm.summary} onChange={e => setDaybookForm({ ...daybookForm, summary: e.target.value })} placeholder="Daily note" className="h-24 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <button className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700">Log entry</button>
            </div>
          </form>
        </section>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Daybook</h2>
              <p className="mt-1 text-xs text-slate-500">Daily activity trail for client follow-ups and internal handoffs.</p>
            </div>
            <StatusBadge value={daybook.isLoading ? 'pending' : `${daybook.data?.length || 0} entries`} />
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-4">
            <input type="date" value={daybookFilters.target_date} onChange={e => setDaybookFilters({ ...daybookFilters, target_date: e.target.value })} className="rounded-lg border px-3 py-2 text-sm" />
            <ClientSelect clients={clients.data || []} value={daybookFilters.client_id} onChange={value => setDaybookFilters({ ...daybookFilters, client_id: value })} />
            <select value={daybookFilters.activity_type} onChange={e => setDaybookFilters({ ...daybookFilters, activity_type: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All activities</option>
              <option value="follow_up">Follow-up</option>
              <option value="client_call">Client call</option>
              <option value="internal_review">Internal review</option>
              <option value="filing">Filing</option>
            </select>
            <select value={daybookFilters.status} onChange={e => setDaybookFilters({ ...daybookFilters, status: e.target.value })} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All statuses</option>
              <option value="open">Open</option>
              <option value="done">Done</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <div className="mt-4 space-y-2">
            {(daybook.data || []).map(entry => (
              <div key={entry.id} className="rounded-md border border-slate-200 px-3 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <p className="text-sm font-medium text-slate-900">{entry.summary}</p>
                  <StatusBadge value={entry.status} />
                </div>
                <p className="mt-1 text-xs text-slate-500">{entry.client_name || 'General'} / {entry.activity_type} / {entry.assigned_to_email || 'Unassigned'}</p>
                <p className="mt-1 text-xs text-slate-400">{entry.created_at ? new Date(entry.created_at).toLocaleString('en-IN') : ''}</p>
              </div>
            ))}
            {!daybook.data?.length && !daybook.isLoading && <p className="py-10 text-center text-sm text-slate-500">No daybook entries match the filters.</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
