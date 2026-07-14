export type Role = 'partner' | 'manager' | 'article';
export type HealthTier = 'green' | 'amber' | 'red';
export type DocStatus =
  | 'pending_upload'
  | 'received'
  | 'pending'
  | 'processing'
  | 'ocr_complete'
  | 'ocr_failed'
  | 'parse_failed'
  | 'failed_validation'
  | 'verified'
  | 'processed';
export type MatchStatus = 'unmatched' | 'exact' | 'tolerance' | 'fuzzy';

export interface User {
  id: string;
  org_id: string;
  email: string;
  role: Role;
  status?: 'active' | 'suspended' | 'offboarded';
}

export interface TeamInvitation {
  id: string;
  org_id: string;
  email: string;
  role: Role;
  status: 'pending' | 'accepted' | 'revoked' | 'expired';
  expires_at: string;
  accepted_at?: string;
  revoked_at?: string;
  created_at: string;
  invite_url?: string;
}

export interface Organization {
  id: string;
  name: string;
  plan: 'starter' | 'pro' | 'premium';
  gstin?: string;
}

export interface Client {
  id: string;
  org_id: string;
  name: string;
  gstin?: string;
  pan?: string;
  tan?: string;
  email?: string;
  whatsapp_number?: string;
  whatsapp_consent_at?: string;
  health_score: number;
  industry?: string;
  entity_type: string;
  cin?: string;
  registered_office?: string;
  benchmark_consent_at?: string;
  status?: 'active' | 'archived';
  client_partition?: string;
  lifecycle_metadata?: Record<string, unknown>;
  deleted_at?: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface DocumentRecord {
  id: string;
  client_id: string;
  doc_type: string;
  source: string;
  status: DocStatus;
  original_filename?: string;
  mime_type?: string;
  file_size_bytes?: number;
  celery_task_id?: string;
  created_at: string;
  processing_started_at?: string;
  processing_completed_at?: string;
  last_pipeline_error_type?: string;
  ocr_json?: Record<string, unknown>;
}

export interface DocumentExtractionRecord {
  id: string;
  supplier_name?: string;
  supplier_gstin?: string;
  invoice_number?: string;
  invoice_date?: string;
  taxable_value?: number | string;
  cgst_amount?: number | string;
  sgst_amount?: number | string;
  igst_amount?: number | string;
  total_amount?: number | string;
  confidence_score?: number | string;
  validation_status: string;
  validation_errors: { code?: string; message?: string }[];
  auto_tags: string[];
  created_at: string;
}

export interface DocumentPipelineEvent {
  id: string;
  stage: string;
  status: string;
  error_type?: string;
  diagnostic_payload?: Record<string, unknown>;
  created_at: string;
}

export interface DocumentPipeline {
  document_id: string;
  status: DocStatus;
  last_pipeline_error_type?: string;
  extractions: DocumentExtractionRecord[];
  events: DocumentPipelineEvent[];
}

export interface TransactionRecord {
  id: string;
  document_id?: string;
  invoice_no?: string;
  vendor_name?: string;
  vendor_gstin?: string;
  amount: number;
  date?: string;
  source?: 'upload' | 'gstr2b';
  match_status: MatchStatus;
  match_confidence?: number;
  anomaly_score?: number;
  fraud_flag?: string;
}

export interface ReconciliationMatchAction {
  id: string;
  client_id: string;
  result_id?: string;
  purchase_transaction_id: string;
  gstr2b_transaction_id?: string;
  action_type: 'manual_match' | 'unmatch' | 'rollback';
  previous_status?: MatchStatus;
  previous_confidence?: number;
  new_status: MatchStatus;
  new_confidence?: number;
  reason?: string;
  evidence: Record<string, unknown>;
  created_by_user_id?: string;
  created_at: string;
}

export interface ReconciliationConfig {
  client_id: string;
  amount_tolerance: number;
  date_tolerance: number;
  fuzzy_threshold: number;
}

export interface ReconciliationResult {
  id: string;
  client_id: string;
  period: string;
  total_purchase?: number;
  total_gstr2b?: number;
  matched_count?: number;
  unmatched_count?: number;
  mismatch_value?: number;
  status: 'queued' | 'running' | 'completed' | 'failed';
  task_id?: string;
  error_message?: string;
  input_summary: Record<string, number>;
  completed_at?: string;
  run_at: string;
}

export interface AutopilotSummary {
  open_count: number;
  by_severity: Record<string, number>;
  by_source: Record<string, number>;
  total_impact: number;
  urgent_due: number;
  estimated_review_minutes: number;
  time_saved_minutes: number;
  top_actions?: { label: string; count: number }[];
  last_sync_at?: string;
  stale_sync_count?: number;
  failed_sync_count?: number;
  followup_by_status?: Record<string, number>;
  blocked_followups?: number;
  headline: string;
}

export interface AutopilotException {
  id: string;
  client_id?: string;
  client_name?: string;
  source_type: string;
  source_id?: string;
  title: string;
  description: string;
  severity: 'critical' | 'high' | 'medium' | 'low';
  impact_amount: number;
  due_date?: string;
  status: string;
  owner_id?: string;
  owner_email?: string;
  evidence: Record<string, unknown>;
  recommended_actions: { label: string; action_type: string }[];
  reviewed_by?: string;
  reviewed_by_email?: string;
  reviewed_at?: string;
  generated_at?: string;
  updated_at?: string;
}

export interface AutopilotReviewAction {
  id: string;
  action_type: string;
  notes?: string;
  payload: Record<string, unknown>;
  created_by?: string;
  created_by_email?: string;
  created_at?: string;
}

export interface AutopilotFollowup {
  id: string;
  client_id: string;
  client_name?: string;
  exception_id?: string;
  exception_title?: string;
  channel: string;
  template: string;
  message: string;
  status: string;
  scheduled_at?: string;
  sent_at?: string;
  response_summary?: string;
  created_at?: string;
}

export interface AutopilotFollowupList {
  items: AutopilotFollowup[];
  totals: {
    followups: number;
    by_status: Record<string, number>;
    by_channel: Record<string, number>;
    blocked: number;
  };
  skip: number;
  limit: number;
}

export interface AutopilotExceptionDetail extends AutopilotException {
  actions: AutopilotReviewAction[];
  followups: AutopilotFollowup[];
}

export interface AutopilotSyncRun {
  id: string;
  client_id?: string;
  client_name?: string;
  source: string;
  source_name?: string;
  period?: string;
  status: string;
  records_received: number;
  records_imported: number;
  records_failed: number;
  summary: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}

export interface AutopilotSyncRunList {
  items: AutopilotSyncRun[];
  totals: {
    runs: number;
    records_received: number;
    records_imported: number;
    records_failed: number;
    failed_runs: number;
  };
  skip: number;
  limit: number;
}

export interface AutopilotOverview {
  summary: AutopilotSummary;
  exceptions: AutopilotException[];
  last_sync_runs: AutopilotSyncRun[];
}

export interface TallyConnectorConfig {
  connector_name: string;
  version: string;
  environment: string;
  sync_url: string;
  method: string;
  content_type: string;
  headers: Record<string, string>;
  auth: Record<string, unknown>;
  limits: Record<string, unknown>;
  supported_sources: { key: string; label: string }[];
  required_fields: string[];
  canonical_fields: Record<string, Record<string, unknown>>;
  field_aliases: Record<string, string[]>;
  validation_rules: string[];
  sample_request: Record<string, unknown>;
  sample_record: Record<string, unknown>;
  sample_success_shape: Record<string, unknown>;
}
