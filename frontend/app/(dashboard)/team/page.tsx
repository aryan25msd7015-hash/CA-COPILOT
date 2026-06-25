'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Role, TeamInvitation, User } from '@/types';
import StatusBadge from '@/components/shared/StatusBadge';

interface CapacityRow {
  user_id: string;
  email: string;
  role: string;
  attendance_status: string;
  hours_available: number;
  hours_booked: number;
  utilization: number;
  open_tasks: number;
}

interface AttendanceRow {
  id: string;
  user_id: string;
  email: string;
  work_date: string;
  status: string;
  hours_available: number;
  hours_booked: number;
  utilization: number;
  notes?: string;
}

interface TeamOverview {
  staff_count: number;
  present_count: number;
  hours_available: number;
  hours_booked: number;
  utilization: number;
  overloaded_count: number;
  underutilized_count: number;
  attendance_by_status: Record<string, number>;
  role_counts: Record<string, number>;
  capacity: CapacityRow[];
}

const today = new Date().toISOString().slice(0, 10);

export default function TeamPage() {
  const [targetDate, setTargetDate] = useState(today);
  const [attendanceStatus, setAttendanceStatus] = useState('');
  const [form, setForm] = useState({
    user_id: '',
    work_date: today,
    status: 'present',
    hours_available: '8',
    hours_booked: '0',
    notes: '',
  });
  const [inviteForm, setInviteForm] = useState<{ email: string; role: Role }>({ email: '', role: 'article' });
  const [lastInviteUrl, setLastInviteUrl] = useState('');

  const overview = useQuery<TeamOverview>({
    queryKey: ['team-overview', targetDate],
    queryFn: () => api.get('/team/overview', { params: { target_date: targetDate } }).then(r => r.data),
  });
  const attendance = useQuery<AttendanceRow[]>({
    queryKey: ['team-attendance', targetDate, attendanceStatus],
    queryFn: () => api.get('/team/attendance', {
      params: {
        target_date: targetDate,
        status: attendanceStatus || undefined,
      },
    }).then(r => r.data),
  });
  const users = useQuery<User[]>({ queryKey: ['users'], queryFn: () => api.get('/users').then(r => r.data).catch(() => []) });
  const invitations = useQuery<TeamInvitation[]>({ queryKey: ['team-invitations'], queryFn: () => api.get('/users/invitations').then(r => r.data).catch(() => []) });

  async function saveAttendance(event: FormEvent) {
    event.preventDefault();
    await api.post('/team/attendance', {
      ...form,
      user_id: form.user_id || null,
      hours_available: Number(form.hours_available),
      hours_booked: Number(form.hours_booked),
    });
    setTargetDate(form.work_date);
    await Promise.all([overview.refetch(), attendance.refetch()]);
  }

  async function quickMark(userId: string, status: string, hours = 8) {
    await api.post('/team/attendance', {
      user_id: userId,
      work_date: targetDate,
      status,
      hours_available: status === 'leave' ? 0 : hours,
      hours_booked: 0,
    });
    await Promise.all([overview.refetch(), attendance.refetch()]);
  }

  async function sendInvite(event: FormEvent) {
    event.preventDefault();
    const response = await api.post<TeamInvitation>('/users/invitations', inviteForm);
    setLastInviteUrl(response.data.invite_url || '');
    setInviteForm({ email: '', role: 'article' });
    await invitations.refetch();
  }

  async function revokeInvite(inviteId: string) {
    await api.post(`/users/invitations/${inviteId}/revoke`);
    await invitations.refetch();
  }

  const metrics = [
    ['Staff', overview.data?.staff_count || 0],
    ['Present', overview.data?.present_count || 0],
    ['Available hrs', overview.data?.hours_available || 0],
    ['Booked hrs', overview.data?.hours_booked || 0],
    ['Utilization', `${overview.data?.utilization || 0}%`],
    ['Overloaded', overview.data?.overloaded_count || 0],
    ['Underused', overview.data?.underutilized_count || 0],
    ['Pending invites', (invitations.data || []).filter(item => item.status === 'pending').length],
  ];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-950">Team & Attendance</h1>
          <p className="text-sm text-slate-500">Staff presence, available hours, booked capacity, and open task load.</p>
        </div>
        <input type="date" value={targetDate} onChange={e => setTargetDate(e.target.value)} className="rounded-lg border px-3 py-2 text-sm" />
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
            <h2 className="text-sm font-semibold text-slate-900">Capacity board</h2>
            <p className="mt-1 text-xs text-slate-500">Daily workload view by person, attendance status, utilization, and open tasks.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {Object.entries(overview.data?.attendance_by_status || {}).map(([status, count]) => (
              <span key={status} className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{status}: {count}</span>
            ))}
          </div>
        </div>
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-3">User</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Attendance</th>
                <th className="px-4 py-3">Available</th>
                <th className="px-4 py-3">Booked</th>
                <th className="px-4 py-3">Utilization</th>
                <th className="px-4 py-3">Open tasks</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {(overview.data?.capacity || []).map(row => (
                <tr key={row.user_id} className="border-t border-slate-100">
                  <td className="px-4 py-3 font-medium text-slate-900">{row.email}</td>
                  <td className="px-4 py-3 text-slate-600">{row.role}</td>
                  <td className="px-4 py-3"><StatusBadge value={row.attendance_status} /></td>
                  <td className="px-4 py-3 text-slate-600">{row.hours_available}</td>
                  <td className="px-4 py-3 text-slate-600">{row.hours_booked}</td>
                  <td className="px-4 py-3">
                    <div className="h-2 w-28 rounded-full bg-slate-100">
                      <div className={`h-2 rounded-full ${row.utilization >= 100 ? 'bg-red-500' : row.utilization < 50 ? 'bg-amber-500' : 'bg-blue-600'}`} style={{ width: `${Math.min(row.utilization, 100)}%` }} />
                    </div>
                    <p className="mt-1 text-xs text-slate-500">{row.utilization}%</p>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{row.open_tasks}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      <button onClick={() => quickMark(row.user_id, 'present')} className="rounded-md border px-2 py-1 text-xs">Present</button>
                      <button onClick={() => quickMark(row.user_id, 'leave', 0)} className="rounded-md border px-2 py-1 text-xs">Leave</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[.7fr_1.3fr]">
        <form onSubmit={saveAttendance} className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Attendance entry</h2>
          <div className="mt-3 space-y-3">
            <select value={form.user_id} onChange={e => setForm({ ...form, user_id: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="">Me</option>
              {(users.data || []).map(user => <option key={user.id} value={user.id}>{user.email}</option>)}
            </select>
            <input type="date" value={form.work_date} onChange={e => setForm({ ...form, work_date: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <select value={form.status} onChange={e => setForm({ ...form, status: e.target.value })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="present">Present</option>
              <option value="half_day">Half day</option>
              <option value="leave">Leave</option>
              <option value="remote">Remote</option>
            </select>
            <div className="grid grid-cols-2 gap-2">
              <input type="number" step="0.25" value={form.hours_available} onChange={e => setForm({ ...form, hours_available: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
              <input type="number" step="0.25" value={form.hours_booked} onChange={e => setForm({ ...form, hours_booked: e.target.value })} className="rounded-md border border-slate-300 px-3 py-2 text-sm" />
            </div>
            <textarea value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} placeholder="Notes" className="h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Save attendance</button>
          </div>
        </form>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-slate-900">Attendance log</h2>
              <p className="mt-1 text-xs text-slate-500">Marked attendance records for the selected date.</p>
            </div>
            <select value={attendanceStatus} onChange={e => setAttendanceStatus(e.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All statuses</option>
              <option value="present">Present</option>
              <option value="remote">Remote</option>
              <option value="half_day">Half day</option>
              <option value="leave">Leave</option>
            </select>
          </div>
          <div className="mt-3 grid gap-2 md:grid-cols-2">
            {(attendance.data || []).map(row => (
              <div key={row.id} className="rounded-md border border-slate-200 p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-semibold text-slate-900">{row.email}</p>
                  <StatusBadge value={row.status} />
                </div>
                <p className="mt-1 text-xs text-slate-500">{row.hours_booked}/{row.hours_available} hours / {row.utilization}% utilized</p>
                {row.notes && <p className="mt-2 text-xs text-slate-600">{row.notes}</p>}
              </div>
            ))}
            {!attendance.data?.length && !attendance.isLoading && <p className="py-8 text-sm text-slate-500">No attendance records match the filters.</p>}
          </div>
        </section>
      </div>

      <div className="grid gap-4 xl:grid-cols-[.75fr_1.25fr]">
        <form onSubmit={sendInvite} className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Invite team member</h2>
          <div className="mt-3 space-y-3">
            <input type="email" required value={inviteForm.email} onChange={e => setInviteForm({ ...inviteForm, email: e.target.value })} placeholder="member@firm.com" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm" />
            <select value={inviteForm.role} onChange={e => setInviteForm({ ...inviteForm, role: e.target.value as Role })} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              <option value="article">Article</option>
              <option value="manager">Manager</option>
              <option value="partner">Partner</option>
            </select>
            <button className="w-full rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white">Generate invitation</button>
            {lastInviteUrl && <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-900"><p className="font-semibold">Activation link</p><p className="mt-1 break-all">{lastInviteUrl}</p></div>}
          </div>
        </form>

        <section className="rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 p-4">
            <h2 className="text-sm font-semibold text-slate-900">Invitation queue</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">Email</th>
                  <th className="px-4 py-3">Role</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3">Expires</th>
                  <th className="px-4 py-3"></th>
                </tr>
              </thead>
              <tbody>
                {(invitations.data || []).map(invite => (
                  <tr key={invite.id} className="border-t border-slate-100">
                    <td className="px-4 py-3 font-medium text-slate-900">{invite.email}</td>
                    <td className="px-4 py-3 text-slate-600">{invite.role}</td>
                    <td className="px-4 py-3"><StatusBadge value={invite.status} /></td>
                    <td className="px-4 py-3 text-slate-600">{new Date(invite.expires_at).toLocaleString()}</td>
                    <td className="px-4 py-3 text-right">{invite.status === 'pending' && <button type="button" onClick={() => revokeInvite(invite.id)} className="rounded-md border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700">Revoke</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  );
}
