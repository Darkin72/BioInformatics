export type RequestStatus =
  | 'pending'
  | 'processing'
  | 'completed'
  | 'failed'
  | 'retrying'
  | 'cancelled'

export type UserRole = 'viewer' | 'operator' | 'admin'

export interface AuthUser {
  username: string
  display_name: string
  roles: UserRole[]
}

export interface LoginCredentials {
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
}

export interface LatestPrediction {
  protein_id: string
  request_id: string
  predicted_at: string
  model_version: string
  top_terms: PredictionTerm[]
  confidence_summary?: string
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
  recent_predictions: LatestPrediction[]
  recent_failed_requests: InferenceRequest[]
  updated_at: string
}

export interface CreateInferenceRequestPayload {
  protein_id: string
  sequence: string
  source: string
  metadata?: Record<string, unknown>
}
