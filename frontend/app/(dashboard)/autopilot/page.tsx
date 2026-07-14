'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { AutopilotException, AutopilotExceptionDetail, AutopilotFollowupList, AutopilotOverview, AutopilotSyncRunList, Client, TallyConnectorConfig, User } from '@/types';
import ClientSelect from '@/components/shared/ClientSelect';
import PageHeader from '@/components/shared/PageHeader';
import StatusBadge from '@/components/shared/StatusBadge';

const SAMPLE_TALLY_ROWS = JSON.stringify([
  {
    'Voucher No': 'PUR-1042',
    Date: new Date().toLocaleDateString('en-GB'),
    'Party Name': 'Demo Supplier Pvt Ltd',
    'GSTIN/UIN of Party': '27ABCDE1234F1Z5',
    Amount: '49,500',
    'Tax Amount': '8,910',
  },
], null, 2);

const SOURCE_LABELS: Record<string, string> = {
  gst_reconciliation: 'GST reconciliation',
  msme_43bh: 'MSME 43B(h)',
  anomaly: 'Audit anomaly',
  deadline: 'Deadline risk',
  certificate_review: 'Certificate review',
  secretarial_review: 'Secretarial review',
  lease_review: 'Lease review',
  rfp_review: 'RFP approval',
  tally_transaction: 'Tally voucher',
  profitability: 'Profitability',
};

const SEVERITY_CLASS: Record<string, string> = {
  critical: 'border-red-300 bg-red-50 text-red-800',
  high: 'border-orange-300 bg-orange-50 text-orange-800',
  medium: 'border-amber-300 bg-amber-50 text-amber-800',
  low: 'border-blue-300 bg-blue-50 text-blue-800',
};

type RefreshResult = {
  created: number;
  updated: number;
  skipped_closed: number;
  auto_resolved: number;
  candidate_count: number;
  dry_run: boolean;
  duration_ms: number;
  scope: {
    client_id: string | null;
    client_name: string;
  };
  before: {
    open_count: number;
    critical_count: number;
    high_count: number;
    total_impact: number;
  };
  after: {
    open_count: number;
    critical_count: number;
    high_count: number;
    total_impact: number;
  };
};

function money(value: number) {
  return `INR ${Number(value || 0).toLocaleString('en-IN')}`;
}

function minutes(value: number) {
  if (value < 60) return `${Math.round(value)} min`;
  return `${Math.floor(value / 60)}h ${Math.round(value % 60)}m`;
}

export default function AutopilotPage() {
  const [clientId, setClientId] = useState('');
  const [refreshClientId, setRefreshClientId] = useState('');
  const [refreshResult, setRefreshResult] = useState<RefreshResult | null>(null);
  const [queueStatus, setQueueStatus] = useState('open,in_review');
  const [queueSeverity, setQueueSeverity] = useState('');
  const [queueSource, setQueueSource] = useState('');
  const [queueClientId, setQueueClientId] = useState('');
  const [syncClientId, setSyncClientId] = useState('');
  const [syncStatus, setSyncStatus] = useState('');
  const [syncPeriod, setSyncPeriod] = useState('');
  const [followupClientId, setFollowupClientId] = useState('');
  const [followupStatus, setFollowupStatus] = useState('');
  const [followupChannel, setFollowupChannel] = useState('');
  const [newFollowupClientId, setNewFollowupClientId] = useState('');
  const [newFollowupChannel, setNewFollowupChannel] = useState('whatsapp');
  const [newFollowupSendNow, setNewFollowupSendNow] = useState(false);
  const [newFollowupMessage, setNewFollowupMessage] = useState('');
  const [ownerId, setOwnerId] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [recordsText, setRecordsText] = useState(SAMPLE_TALLY_ROWS);
  const [selected, setSelected] = useState<AutopilotException | null>(null);
  const [message, setMessage] = useState('');

  const clients = useQuery<Client[]>({
    queryKey: ['clients'],
    queryFn: () => api.get('/clients').then(r => r.data),
  });

  const users = useQuery<User[]>({
    queryKey: ['users'],
    queryFn: () => api.get('/users').then(r => r.data),
  });

  const overview = useQuery<AutopilotOverview>({
    queryKey: ['autopilot-overview'],
    queryFn: () => api.get('/autopilot/overview').then(r => r.data),
  });

  const exceptionList = useQuery<AutopilotException[]>({
    queryKey: ['autopilot-exceptions', queueStatus, queueSeverity, queueSource, queueClientId],
    queryFn: () => api.get('/autopilot/exceptions', {
      params: {
        status: queueStatus,
        severity: queueSeverity || undefined,
        source_type: queueSource || undefined,
        client_id: queueClientId || undefined,
        limit: 250,
      },
    }).then(r => r.data),
  });

  const selectedDetail = useQuery<AutopilotExceptionDetail>({
    queryKey: ['autopilot-exception-detail', selected?.id],
    queryFn: () => api.get(`/autopilot/exceptions/${selected?.id}`).then(r => r.data),
    enabled: Boolean(selected?.id),
  });

  const connectorConfig = useQuery<TallyConnectorConfig>({
    queryKey: ['tally-connector-config'],
    queryFn: () => api.get('/autopilot/tally/connector-config').then(r => r.data),
  });

  const syncRuns = useQuery<AutopilotSyncRunList>({
    queryKey: ['autopilot-sync-runs', syncClientId, syncStatus, syncPeriod],
    queryFn: () => api.get('/autopilot/sync-runs', {
      params: {
        client_id: syncClientId || undefined,
        status: syncStatus || undefined,
        period: syncPeriod || undefined,
        limit: 100,
      },
    }).then(r => r.data),
  });

  const followups = useQuery<AutopilotFollowupList>({
    queryKey: ['autopilot-followups', followupClientId, followupStatus, followupChannel],
    queryFn: () => api.get('/autopilot/followups', {
      params: {
        client_id: followupClientId || undefined,
        status: followupStatus || undefined,
        channel: followupChannel || undefined,
        limit: 100,
      },
    }).then(r => r.data),
  });

  const selectedFresh = useMemo(() => {
    if (!selected) return null;
    return selectedDetail.data || exceptionList.data?.find(item => item.id === selected.id) || selected;
  }, [exceptionList.data, selected, selectedDetail.data]);

  useEffect(() => {
    setOwnerId(selectedFresh?.owner_id || '');
    setReviewNote('');
  }, [selectedFresh?.id, selectedFresh?.owner_id]);

  async function refreshInbox(dryRun = false) {
    setMessage('');
    const response = await api.post('/autopilot/refresh', {
      client_id: refreshClientId || undefined,
      dry_run: dryRun,
    });
    setRefreshResult(response.data);
    if (!dryRun) {
      await overview.refetch();
      await exceptionList.refetch();
    }
    const verb = dryRun ? 'Preview ready' : 'Autopilot refreshed';
    setMessage(`${verb} for ${response.data.scope.client_name}: ${response.data.created} create, ${response.data.updated} update, ${response.data.auto_resolved} auto-resolve.`);
  }

  async function syncTally() {
    setMessage('');
    if (!clientId) {
      setMessage('Select a client before syncing Tally data.');
      return;
    }
    let records: Record<string, unknown>[];
    try {
      records = JSON.parse(recordsText);
      if (!Array.isArray(records)) throw new Error('Expected an array');
    } catch {
      setMessage('Tally records must be a JSON array.');
      return;
    }
    const response = await api.post('/autopilot/tally/sync', {
      client_id: clientId,
      source_name: 'Manual Tally import',
      period,
      records,
    });
    await overview.refetch();
    await syncRuns.refetch();
    setMessage(`${response.data.sync_run.records_imported} Tally records imported; ${response.data.autopilot_refresh.candidate_count} exception candidates evaluated.`);
  }

  async function reviewException(item: AutopilotException, status: string, actionType: string) {
    await api.patch(`/autopilot/exceptions/${item.id}`, {
      status,
      action_type: actionType,
      notes: reviewNote || (status === 'resolved' ? 'Reviewed and closed from Autopilot.' : `Marked ${status} from Autopilot.`),
    });
    await overview.refetch();
    await exceptionList.refetch();
    await selectedDetail.refetch();
    setReviewNote('');
  }

  async function assignOwner(item: AutopilotException) {
    await api.patch(`/autopilot/exceptions/${item.id}`, {
      owner_id: ownerId || undefined,
      clear_owner: !ownerId,
      action_type: ownerId ? 'assign_owner' : 'clear_owner',
      notes: ownerId ? 'Owner assigned from Autopilot.' : 'Owner cleared from Autopilot.',
    });
    await exceptionList.refetch();
    await selectedDetail.refetch();
  }

  async function sendFollowup(item: AutopilotException) {
    await api.post('/autopilot/followups', {
      exception_id: item.id,
      message: `Dear ${item.client_name || 'Client'}, our review has identified this pending item: ${item.title}. Please share the required support so we can close it.`,
    });
    await overview.refetch();
    await exceptionList.refetch();
    await selectedDetail.refetch();
    await followups.refetch();
    setMessage('Follow-up drafted and linked to the exception.');
  }

  async function createClientFollowup() {
    setMessage('');
    if (!newFollowupClientId) {
      setMessage('Select a client before creating a follow-up.');
      return;
    }
    await api.post('/autopilot/followups', {
      client_id: newFollowupClientId,
      channel: newFollowupChannel,
      message: newFollowupMessage,
      send_now: newFollowupSendNow,
    });
    await overview.refetch();
    await followups.refetch();
    setNewFollowupMessage('');
    setMessage(newFollowupSendNow ? 'Follow-up created and send attempt recorded.' : 'Follow-up draft created.');
  }

  const summary = overview.data?.summary;
  const exceptions = exceptionList.data || [];
  const sourceOptions = Object.entries(SOURCE_LABELS);
  const detail = selectedDetail.data;
  const hasSelectedDetail = Boolean(detail && selectedFresh && detail.id === selectedFresh.id);
  const detailActions = hasSelectedDetail && detail ? detail.actions : [];
  const detailFollowups = hasSelectedDetail && detail ? detail.followups : [];

  return (
    <div className="space-y-5">
      <PageHeader
        title="CA Exception Autopilot"
        subtitle="One inbox for Tally syncs, compliance exposure, missing evidence, review approvals, and client follow-ups."
        actions={
          <button onClick={() => refreshInbox(false)} className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white">
            Refresh inbox
          </button>
        }
      />

      {summary && (
        <div className="space-y-4 rounded-2xl border bg-gradient-to-br from-gray-950 to-blue-950 p-5 text-white">
          <div>
            <p className="text-sm text-blue-100">{summary.headline}</p>
            <div className="mt-4 grid gap-3 sm:grid-cols-5">
              {[
                ['Open exceptions', summary.open_count],
                ['Exposure', money(summary.total_impact)],
                ['Urgent in 3 days', summary.urgent_due],
                ['Review effort', minutes(summary.estimated_review_minutes)],
                ['Time saved', minutes(summary.time_saved_minutes)],
              ].map(([label, value]) => (
                <div key={label} className="rounded-xl border border-white/10 bg-white/10 p-3">
                  <p className="text-xs text-blue-100">{label}</p>
                  <p className="mt-1 text-lg font-semibold">{value}</p>
                </div>
              ))}
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            <div className="rounded-xl border border-white/10 bg-white/10 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-blue-100">Severity mix</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(summary.by_severity || {}).map(([key, value]) => <span key={key} className="rounded-full bg-white/10 px-2 py-1 text-xs">{key}: {value}</span>)}
              </div>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/10 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-blue-100">Sync health</p>
              <p className="mt-2 text-xs text-blue-100">Last sync: {summary.last_sync_at ? new Date(summary.last_sync_at).toLocaleString('en-IN') : 'None'}</p>
              <p className="mt-1 text-xs text-blue-100">Stale: {summary.stale_sync_count || 0} | Failed/errors: {summary.failed_sync_count || 0}</p>
            </div>
            <div className="rounded-xl border border-white/10 bg-white/10 p-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-blue-100">Follow-ups</p>
              <p className="mt-2 text-xs text-blue-100">Blocked/failed: {summary.blocked_followups || 0}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {Object.entries(summary.followup_by_status || {}).map(([key, value]) => <span key={key} className="rounded-full bg-white/10 px-2 py-1 text-xs">{key}: {value}</span>)}
              </div>
            </div>
          </div>
          {!!summary.top_actions?.length && <div className="rounded-xl border border-white/10 bg-white/10 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-blue-100">Recommended actions</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {summary.top_actions.map(action => <span key={action.label} className="rounded-full bg-white/10 px-2 py-1 text-xs">{action.label}: {action.count}</span>)}
            </div>
          </div>
          }
        </div>
      )}

      <section className="rounded-xl border bg-white p-4">
        <div className="grid gap-4 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Refresh control</h2>
            <p className="mt-1 text-xs text-gray-500">Preview exception changes before updating the live partner queue.</p>
            <div className="mt-3 max-w-sm">
              <ClientSelect clients={clients.data || []} value={refreshClientId} onChange={setRefreshClientId} />
              <button onClick={() => setRefreshClientId('')} className="mt-2 text-xs font-medium text-gray-500 hover:text-gray-900">
                Use all clients
              </button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => refreshInbox(true)} className="rounded-lg border px-3 py-2 text-sm font-medium text-gray-700">
              Preview refresh
            </button>
            <button onClick={() => refreshInbox(false)} className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white">
              Apply refresh
            </button>
          </div>
        </div>
        {refreshResult && (
          <div className="mt-4 grid gap-3 sm:grid-cols-5">
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Scope</p>
              <p className="mt-1 text-sm font-semibold text-gray-900">{refreshResult.scope.client_name}</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Candidates</p>
              <p className="mt-1 text-sm font-semibold text-gray-900">{refreshResult.candidate_count}</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Queue delta</p>
              <p className="mt-1 text-sm font-semibold text-gray-900">{refreshResult.before.open_count} to {refreshResult.after.open_count}</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Actions</p>
              <p className="mt-1 text-sm font-semibold text-gray-900">+{refreshResult.created} / ~{refreshResult.updated} / -{refreshResult.auto_resolved}</p>
            </div>
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-xs text-gray-500">Runtime</p>
              <p className="mt-1 text-sm font-semibold text-gray-900">{refreshResult.duration_ms} ms {refreshResult.dry_run ? '(preview)' : ''}</p>
            </div>
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-[1.4fr_.9fr]">
        <section className="rounded-xl border bg-white p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold text-gray-900">Partner review queue</h2>
              <p className="text-xs text-gray-500">Exceptions are ranked by severity, due date, and financial exposure.</p>
            </div>
            <StatusBadge value={exceptionList.isLoading ? 'pending' : `${exceptions.length} shown`} />
          </div>
          <div className="mb-3 grid gap-2 md:grid-cols-4">
            <select value={queueStatus} onChange={event => setQueueStatus(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="open,in_review">Active</option>
              <option value="open">Open</option>
              <option value="in_review">In review</option>
              <option value="approved,resolved,dismissed">Closed</option>
              <option value="">All statuses</option>
            </select>
            <select value={queueSeverity} onChange={event => setQueueSeverity(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
            <select value={queueSource} onChange={event => setQueueSource(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
              <option value="">All sources</option>
              {sourceOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
            <ClientSelect clients={clients.data || []} value={queueClientId} onChange={setQueueClientId} />
          </div>
          <div className="space-y-3">
            {exceptions.map(item => (
              <button
                key={item.id}
                onClick={() => setSelected(item)}
                className={`w-full rounded-xl border p-4 text-left transition hover:shadow-sm ${selectedFresh?.id === item.id ? 'border-blue-500 ring-2 ring-blue-100' : 'border-gray-200'}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2 py-0.5 text-xs font-semibold ${SEVERITY_CLASS[item.severity] || SEVERITY_CLASS.medium}`}>
                        {item.severity}
                      </span>
                      <span className="text-xs text-gray-500">{SOURCE_LABELS[item.source_type] || item.source_type}</span>
                      <StatusBadge value={item.status} />
                    </div>
                    <h3 className="mt-2 text-sm font-semibold text-gray-900">{item.title}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-gray-600">{item.description}</p>
                    <p className="mt-2 text-xs text-gray-500">Owner: {item.owner_email || 'Unassigned'}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm font-semibold text-gray-900">{money(item.impact_amount)}</p>
                    {item.due_date && <p className="text-xs text-gray-500">Due {item.due_date}</p>}
                  </div>
                </div>
              </button>
            ))}
            {!exceptions.length && !exceptionList.isLoading && (
              <div className="rounded-xl border border-dashed p-8 text-center text-sm text-gray-500">
                No exceptions match the selected filters.
              </div>
            )}
          </div>
        </section>

        <section className="space-y-4">
          <div className="rounded-xl border bg-white p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-gray-900">Tally connector config</h2>
                <p className="mt-1 text-xs text-gray-500">{connectorConfig.data?.connector_name || 'Connector'} {connectorConfig.data?.version || ''}</p>
              </div>
              <StatusBadge value={connectorConfig.isLoading ? 'pending' : connectorConfig.data?.environment || 'ready'} />
            </div>
            {connectorConfig.data && (
              <div className="mt-3 space-y-3">
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Sync endpoint</p>
                  <p className="mt-1 break-all font-mono text-xs text-gray-700">{connectorConfig.data.method} {connectorConfig.data.sync_url}</p>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold text-gray-500">Required</p>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {connectorConfig.data.required_fields.map(field => <span key={field} className="rounded-full bg-gray-100 px-2 py-1 text-xs text-gray-700">{field}</span>)}
                    </div>
                  </div>
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold text-gray-500">Limits</p>
                    <p className="mt-2 text-xs text-gray-600">Batch: {String(connectorConfig.data.limits.recommended_batch_size)} / Max: {String(connectorConfig.data.limits.max_records_per_request)}</p>
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <p className="text-xs font-semibold text-gray-500">Supported sources</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {connectorConfig.data.supported_sources.map(source => <span key={source.key} className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-700">{source.label}</span>)}
                  </div>
                </div>
                <div className="rounded-lg border p-3">
                  <p className="text-xs font-semibold text-gray-500">Field aliases</p>
                  <div className="mt-2 grid gap-2 text-xs text-gray-600">
                    {Object.entries(connectorConfig.data.field_aliases).map(([field, aliases]) => (
                      <p key={field}><span className="font-semibold text-gray-800">{field}:</span> {aliases.slice(0, 5).join(', ')}</p>
                    ))}
                  </div>
                </div>
                <div className="rounded-lg bg-gray-950 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-300">Sample request</p>
                  <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap text-xs text-gray-100">
                    {JSON.stringify(connectorConfig.data.sample_request, null, 2)}
                  </pre>
                </div>
              </div>
            )}
          </div>

          <div className="rounded-xl border bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Tally sync intake</h2>
            <p className="mt-1 text-xs text-gray-500">Use this for manual testing. The desktop connector posts to the same endpoint.</p>
            <div className="mt-3 space-y-3">
              <ClientSelect clients={clients.data || []} value={clientId} onChange={setClientId} />
              <input value={period} onChange={event => setPeriod(event.target.value)} className="w-full rounded-lg border px-3 py-2 text-sm" placeholder="2026-06" />
              <textarea
                value={recordsText}
                onChange={event => setRecordsText(event.target.value)}
                className="h-48 w-full rounded-lg border px-3 py-2 font-mono text-xs"
              />
              <button onClick={syncTally} className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white">
                Sync Tally records
              </button>
            </div>
          </div>

          <div className="rounded-xl border bg-white p-4">
            <h2 className="text-sm font-semibold text-gray-900">Selected exception</h2>
            {selectedFresh ? (
              <div className="mt-3 space-y-3">
                <div>
                  <p className="text-sm font-semibold text-gray-900">{selectedFresh.title}</p>
                  <p className="mt-1 text-sm text-gray-600">{selectedFresh.description}</p>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                    <span>Client: {selectedFresh.client_name || 'Unknown'}</span>
                    <span>Owner: {selectedFresh.owner_email || 'Unassigned'}</span>
                    <span>Updated: {selectedFresh.updated_at ? new Date(selectedFresh.updated_at).toLocaleString('en-IN') : '-'}</span>
                  </div>
                </div>
                <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                  <select value={ownerId} onChange={event => setOwnerId(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
                    <option value="">Unassigned</option>
                    {(users.data || []).map(user => <option key={user.id} value={user.id}>{user.email} ({user.role})</option>)}
                  </select>
                  <button onClick={() => assignOwner(selectedFresh)} className="rounded-lg border px-3 py-2 text-sm">
                    Save owner
                  </button>
                </div>
                <textarea
                  value={reviewNote}
                  onChange={event => setReviewNote(event.target.value)}
                  className="h-20 w-full rounded-lg border px-3 py-2 text-sm"
                  placeholder="Review note or CA conclusion"
                />
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Evidence</p>
                  <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap text-xs text-gray-700">
                    {JSON.stringify(selectedFresh.evidence, null, 2)}
                  </pre>
                </div>
                <div className="space-y-2">
                  {(selectedFresh.recommended_actions || []).map(action => (
                    <div key={action.action_type} className="rounded-lg border px-3 py-2 text-xs text-gray-600">
                      {action.label}
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <button onClick={() => sendFollowup(selectedFresh)} className="rounded-lg border px-3 py-2 text-sm">
                    Draft follow-up
                  </button>
                  <button onClick={() => reviewException(selectedFresh, 'in_review', 'start_review')} className="rounded-lg border px-3 py-2 text-sm">
                    In review
                  </button>
                  <button onClick={() => reviewException(selectedFresh, 'resolved', 'ca_conclusion')} className="rounded-lg bg-green-600 px-3 py-2 text-sm text-white">
                    Resolve
                  </button>
                  <button onClick={() => reviewException(selectedFresh, 'dismissed', 'not_applicable')} className="rounded-lg bg-gray-900 px-3 py-2 text-sm text-white">
                    Dismiss
                  </button>
                </div>
                {hasSelectedDetail && (
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Review history</p>
                    <div className="mt-2 space-y-2">
                      {detailActions.map(action => (
                        <div key={action.id} className="rounded-lg bg-gray-50 p-2 text-xs text-gray-600">
                          <p className="font-semibold text-gray-800">{action.action_type} by {action.created_by_email || 'system'}</p>
                          <p>{action.notes || 'No note'}</p>
                          <p className="text-gray-400">{action.created_at ? new Date(action.created_at).toLocaleString('en-IN') : ''}</p>
                        </div>
                      ))}
                      {!detailActions.length && <p className="text-xs text-gray-500">No review actions yet.</p>}
                    </div>
                  </div>
                )}
                {hasSelectedDetail && (
                  <div className="rounded-lg border p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Linked follow-ups</p>
                    <div className="mt-2 space-y-2">
                      {detailFollowups.map(item => (
                        <div key={item.id} className="rounded-lg bg-gray-50 p-2 text-xs text-gray-600">
                          <p><StatusBadge value={item.status} /> <span className="ml-2">{item.channel}</span></p>
                          <p className="mt-1 line-clamp-2">{item.message}</p>
                        </div>
                      ))}
                      {!detailFollowups.length && <p className="text-xs text-gray-500">No follow-ups linked.</p>}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <p className="mt-3 text-sm text-gray-500">Select an exception to review evidence and take action.</p>
            )}
          </div>
        </section>
      </div>

      {message && <p className="rounded-lg border bg-white px-3 py-2 text-sm text-green-700">{message}</p>}

      <section className="rounded-xl border bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Autopilot follow-ups</h2>
            <p className="mt-1 text-xs text-gray-500">Draft, send, and monitor client nudges linked to exception review.</p>
          </div>
          <StatusBadge value={followups.isLoading ? 'pending' : `${followups.data?.totals.followups || 0} follow-ups`} />
        </div>
        <div className="mt-3 grid gap-4 lg:grid-cols-[.8fr_1.2fr]">
          <div className="space-y-3 rounded-lg border p-3">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Create follow-up</h3>
            <ClientSelect clients={clients.data || []} value={newFollowupClientId} onChange={setNewFollowupClientId} />
            <div className="grid gap-2 sm:grid-cols-2">
              <select value={newFollowupChannel} onChange={event => setNewFollowupChannel(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
                <option value="whatsapp">WhatsApp</option>
                <option value="email">Email</option>
                <option value="phone">Phone</option>
              </select>
              <label className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm text-gray-600">
                <input type="checkbox" checked={newFollowupSendNow} onChange={event => setNewFollowupSendNow(event.target.checked)} />
                Send now
              </label>
            </div>
            <textarea
              value={newFollowupMessage}
              onChange={event => setNewFollowupMessage(event.target.value)}
              className="h-24 w-full rounded-lg border px-3 py-2 text-sm"
              placeholder="Leave blank to use the default client document request."
            />
            <button onClick={createClientFollowup} className="w-full rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white">
              Create follow-up
            </button>
          </div>
          <div className="space-y-3">
            <div className="grid gap-2 md:grid-cols-3">
              <ClientSelect clients={clients.data || []} value={followupClientId} onChange={setFollowupClientId} />
              <select value={followupStatus} onChange={event => setFollowupStatus(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
                <option value="">All statuses</option>
                <option value="draft">Draft</option>
                <option value="sent">Sent</option>
                <option value="ready">Ready</option>
                <option value="blocked_no_consent">Blocked: no consent</option>
                <option value="ready_provider_missing">Provider missing</option>
                <option value="failed">Failed</option>
              </select>
              <select value={followupChannel} onChange={event => setFollowupChannel(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
                <option value="">All channels</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="email">Email</option>
                <option value="phone">Phone</option>
              </select>
            </div>
            {followups.data && (
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">Blocked</p>
                  <p className="mt-1 text-sm font-semibold text-gray-900">{followups.data.totals.blocked}</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">By status</p>
                  <p className="mt-1 text-xs text-gray-700">{Object.entries(followups.data.totals.by_status).map(([key, value]) => `${key}: ${value}`).join(' | ') || '-'}</p>
                </div>
                <div className="rounded-lg bg-gray-50 p-3">
                  <p className="text-xs text-gray-500">By channel</p>
                  <p className="mt-1 text-xs text-gray-700">{Object.entries(followups.data.totals.by_channel).map(([key, value]) => `${key}: ${value}`).join(' | ') || '-'}</p>
                </div>
              </div>
            )}
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-xs uppercase text-gray-500">
                  <tr>
                    <th className="px-3 py-2">Client</th>
                    <th className="px-3 py-2">Channel</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2">Linked exception</th>
                    <th className="px-3 py-2">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {(followups.data?.items || []).map(item => (
                    <tr key={item.id} className="border-t align-top">
                      <td className="px-3 py-2">{item.client_name || item.client_id}</td>
                      <td className="px-3 py-2">{item.channel}</td>
                      <td className="px-3 py-2"><StatusBadge value={item.status} /></td>
                      <td className="px-3 py-2">
                        <p className="line-clamp-1">{item.exception_title || '-'}</p>
                        <p className="mt-1 line-clamp-2 text-xs text-gray-500">{item.message}</p>
                      </td>
                      <td className="px-3 py-2">{item.created_at ? new Date(item.created_at).toLocaleString('en-IN') : '-'}</td>
                    </tr>
                  ))}
                  {!followups.data?.items.length && !followups.isLoading && (
                    <tr className="border-t">
                      <td colSpan={5} className="px-3 py-8 text-center text-sm text-gray-500">No follow-ups match the selected filters.</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border bg-white p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold text-gray-900">Tally sync runs</h2>
            <p className="mt-1 text-xs text-gray-500">Connector history, import yield, failed rows, and autopilot handoff diagnostics.</p>
          </div>
          <StatusBadge value={syncRuns.isLoading ? 'pending' : `${syncRuns.data?.totals.runs || 0} runs`} />
        </div>
        <div className="mt-3 grid gap-2 md:grid-cols-3">
          <ClientSelect clients={clients.data || []} value={syncClientId} onChange={setSyncClientId} />
          <select value={syncStatus} onChange={event => setSyncStatus(event.target.value)} className="rounded-lg border bg-white px-3 py-2 text-sm">
            <option value="">All statuses</option>
            <option value="completed">Completed</option>
            <option value="completed_with_errors">Completed with errors</option>
            <option value="failed">Failed</option>
            <option value="processing">Processing</option>
          </select>
          <input value={syncPeriod} onChange={event => setSyncPeriod(event.target.value)} className="rounded-lg border px-3 py-2 text-sm" placeholder="Period e.g. 2026-06" />
        </div>
        {syncRuns.data && (
          <div className="mt-3 grid gap-3 sm:grid-cols-5">
            {[
              ['Runs', syncRuns.data.totals.runs],
              ['Received', syncRuns.data.totals.records_received],
              ['Imported', syncRuns.data.totals.records_imported],
              ['Failed rows', syncRuns.data.totals.records_failed],
              ['Error runs', syncRuns.data.totals.failed_runs],
            ].map(([label, value]) => (
              <div key={label} className="rounded-lg bg-gray-50 p-3">
                <p className="text-xs text-gray-500">{label}</p>
                <p className="mt-1 text-sm font-semibold text-gray-900">{value}</p>
              </div>
            ))}
          </div>
        )}
        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="text-xs uppercase text-gray-500">
              <tr>
                <th className="px-3 py-2">Source</th>
                <th className="px-3 py-2">Client</th>
                <th className="px-3 py-2">Period</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Received</th>
                <th className="px-3 py-2">Imported</th>
                <th className="px-3 py-2">Failed</th>
                <th className="px-3 py-2">Flags</th>
                <th className="px-3 py-2">Completed</th>
              </tr>
            </thead>
            <tbody>
              {(syncRuns.data?.items || []).map(run => (
                <tr key={run.id} className="border-t">
                  <td className="px-3 py-2">{run.source_name || run.source}</td>
                  <td className="px-3 py-2">{run.client_name || '-'}</td>
                  <td className="px-3 py-2">{run.period || '-'}</td>
                  <td className="px-3 py-2"><StatusBadge value={run.status} /></td>
                  <td className="px-3 py-2">{run.records_received}</td>
                  <td className="px-3 py-2">{run.records_imported}</td>
                  <td className="px-3 py-2">{run.records_failed}</td>
                  <td className="px-3 py-2">{String(run.summary?.threshold_flags || 0)}</td>
                  <td className="px-3 py-2">{run.completed_at ? new Date(run.completed_at).toLocaleString('en-IN') : '-'}</td>
                </tr>
              ))}
              {!syncRuns.data?.items.length && !syncRuns.isLoading && (
                <tr className="border-t">
                  <td colSpan={9} className="px-3 py-8 text-center text-sm text-gray-500">No sync runs match the selected filters.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
