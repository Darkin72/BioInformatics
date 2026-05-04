export type RequestStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'retrying'
  | 'cancelled'

export type UserRole = 'user' | 'admin'

export interface AuthUser {
  username: string
  display_name: string
  roles: UserRole[]
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface RegisterCredentials {
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  user: AuthUser
}

export interface InferenceRequest {
  request_id: string
  protein_id: string
  username?: string
  source?: string
  created_at: string
  updated_at?: string
  current_status: RequestStatus
  stage_name?: string
  error_code?: string
  error_message?: string
  retry_count?: number
  model_version?: string
  feature_version?: string
}

export interface PredictionTerm {
  term_id: string
  term_name?: string
  ontology?: 'BP' | 'MF' | 'CC'
  score: number
  definition?: string | null
}

export interface LatestPrediction {
  protein_id: string
  request_id: string
  predicted_at: string
  model_version: string
  top_terms: PredictionTerm[]
  confidence_summary?: string
  server_result?: Record<string, unknown> | null
}

export interface RequestInput {
  protein_id: string
  sequence?: string | null
  sequence_length?: number | null
  source?: string | null
  metadata?: Record<string, unknown> | null
}

export interface RequestResult {
  request: InferenceRequest
  input?: RequestInput | null
  prediction?: LatestPrediction | null
  server_result?: Record<string, unknown> | null
}

export interface PipelineMetricPoint {
  window_start: string
  window_end: string
  metric_name: string
  metric_value: number
  tags?: Record<string, string>
}

export interface DashboardSummary {
  total_today: number
  status_counts: Record<RequestStatus, number>
  avg_latency_ms: number
  p95_latency_ms: number
  error_rate: number
  throughput: PipelineMetricPoint[]
  recent_requests: InferenceRequest[]
  recent_predictions: LatestPrediction[]
  recent_failed_requests: InferenceRequest[]
  error_counts: Record<string, number>
  cassandra_query_patterns: string[]
  cassandra_write_tables: Record<string, number>
  kafka_topics: string[]
  updated_at: string
}

export interface DashboardLiveSnapshot {
  updated_at: string
  avg_latency_ms: number
  p95_latency_ms: number
  throughput: PipelineMetricPoint[]
  status_counts: Partial<Record<RequestStatus, number>>
  error_codes: Record<string, number>
  cassandra: {
    write_tables: Record<string, number>
    active_query_patterns: string[]
    last_event_at?: string | null
  }
}

export interface AdminRequestList {
  items: InferenceRequest[]
  source: string
  limit: number
  table: string
  page: number
  page_size: number
  returned: number
  has_next: boolean
  updated_at: string
}

export interface UserRequestList {
  items: InferenceRequest[]
  source: string
  limit: number
  page: number
  page_size: number
  returned: number
  has_next: boolean
  days: number
  updated_at: string
}

export interface AdminUserItem {
  username: string
  roles: UserRole[]
  is_admin: boolean
}

export interface AdminUserList {
  items: AdminUserItem[]
  returned: number
  updated_at: string
}

export interface ProteinRequestList {
  protein_id: string
  items: InferenceRequest[]
  source: string
  limit: number
  returned: number
  updated_at: string
}

export interface RequestTimelineEvent {
  request_id: string
  event_ts: string
  event_type: string
  stage_name?: string
  status?: string
  message?: string
  latency_ms?: number
  payload?: string
}

export interface CreateInferenceRequestPayload {
  protein_id: string
  sequence: string
  source: string
  metadata?: Record<string, unknown>
}
