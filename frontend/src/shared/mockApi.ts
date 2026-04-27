import type {
  CreateInferenceRequestPayload,
  DashboardSummary,
  InferenceRequest,
  LatestPrediction,
  PipelineMetricPoint,
  RequestStatus,
} from './types'

const now = new Date()

const requests: InferenceRequest[] = [
  {
    request_id: 'demo-processing-001',
    protein_id: 'P12345',
    created_at: minutesAgo(22),
    updated_at: minutesAgo(1),
    current_status: 'processing',
    stage_name: 'model_inference',
    retry_count: 0,
    model_version: 'baseline-cafa6-v1',
    feature_version: 'esm2-lite-v1',
  },
  {
    request_id: 'demo-completed-001',
    protein_id: 'Q8N158',
    created_at: minutesAgo(74),
    updated_at: minutesAgo(69),
    current_status: 'completed',
    stage_name: 'prediction_written',
    retry_count: 0,
    model_version: 'baseline-cafa6-v1',
    feature_version: 'esm2-lite-v1',
  },
  {
    request_id: 'demo-failed-001',
    protein_id: 'BADSEQ01',
    created_at: minutesAgo(38),
    updated_at: minutesAgo(37),
    current_status: 'failed',
    stage_name: 'validation',
    error_code: 'INVALID_SEQUENCE',
    error_message: 'Sequence contains unsupported amino acid symbols.',
    retry_count: 1,
  },
]

const predictions: LatestPrediction[] = [
  {
    protein_id: 'P12345',
    request_id: 'demo-completed-002',
    predicted_at: minutesAgo(9),
    model_version: 'baseline-cafa6-v1',
    confidence_summary: 'High confidence molecular function prediction.',
    top_terms: [
      {
        term_id: 'GO:0005524',
        term_name: 'ATP binding',
        ontology: 'MF',
        score: 0.934,
      },
      {
        term_id: 'GO:0004672',
        term_name: 'protein kinase activity',
        ontology: 'MF',
        score: 0.887,
      },
      {
        term_id: 'GO:0006468',
        term_name: 'protein phosphorylation',
        ontology: 'BP',
        score: 0.842,
      },
    ],
  },
  {
    protein_id: 'Q8N158',
    request_id: 'demo-completed-001',
    predicted_at: minutesAgo(69),
    model_version: 'baseline-cafa6-v1',
    confidence_summary: 'Moderate confidence cellular component prediction.',
    top_terms: [
      {
        term_id: 'GO:0005634',
        term_name: 'nucleus',
        ontology: 'CC',
        score: 0.774,
      },
      {
        term_id: 'GO:0003677',
        term_name: 'DNA binding',
        ontology: 'MF',
        score: 0.713,
      },
    ],
  },
]

const throughput: PipelineMetricPoint[] = Array.from({ length: 8 }).map(
  (_, index) => {
    const start = new Date(now.getTime() - (7 - index) * 5 * 60_000)
    const end = new Date(start.getTime() + 5 * 60_000)

    return {
      window_start: start.toISOString(),
      window_end: end.toISOString(),
      metric_name: 'throughput_per_minute',
      metric_value: [74, 88, 91, 107, 96, 113, 124, 118][index],
      tags: { source: 'mock' },
    }
  },
)

export async function mockCreateInferenceRequest(
  payload: CreateInferenceRequestPayload,
) {
  await delay(350)

  const created: InferenceRequest = {
    request_id: `ui-${crypto.randomUUID()}`,
    protein_id: payload.protein_id,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    current_status: 'pending',
    stage_name: 'queued',
    retry_count: 0,
  }

  requests.unshift(created)
  return created
}

export async function mockGetRequestStatus(requestId: string) {
  await delay(250)
  const request = requests.find((item) => item.request_id === requestId)

  if (!request) {
    throw new Error('Request not found')
  }

  if (request.current_status === 'pending') {
    request.current_status = 'processing'
    request.stage_name = 'validation'
    request.updated_at = new Date().toISOString()
  }

  return request
}

export async function mockGetLatestPrediction(proteinId: string) {
  await delay(250)
  const prediction = predictions.find(
    (item) => item.protein_id.toLowerCase() === proteinId.toLowerCase(),
  )

  if (!prediction) {
    return null
  }

  return prediction
}

export async function mockGetDashboardSummary(): Promise<DashboardSummary> {
  await delay(250)
  const statusCounts = requests.reduce(
    (counts, request) => {
      counts[request.current_status] += 1
      return counts
    },
    {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
      retrying: 0,
      cancelled: 0,
    } satisfies Record<RequestStatus, number>,
  )

  return {
    total_today: 28418,
    status_counts: statusCounts,
    avg_latency_ms: 1280,
    p95_latency_ms: 3420,
    error_rate: 0.018,
    throughput,
    recent_predictions: predictions,
    recent_failed_requests: requests.filter(
      (request) => request.current_status === 'failed',
    ),
    updated_at: new Date().toISOString(),
  }
}

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function minutesAgo(minutes: number) {
  return new Date(now.getTime() - minutes * 60_000).toISOString()
}
