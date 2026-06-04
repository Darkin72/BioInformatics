import { EVENTS_BASE_URL, apiRequest } from '../../shared/apiClient'
import type { DashboardLiveSnapshot, DashboardSummary } from '../../shared/types'

export function getDashboardSummary() {
  return apiRequest<DashboardSummary>(
    '/api/metrics/pipeline/summary?window=minute&request_limit=200',
  )
}

export function openDashboardEvents(
  onSnapshot: (snapshot: DashboardLiveSnapshot) => void,
  onPipelineEvent: () => void,
  onError: () => void,
) {
  const source = new EventSource(`${EVENTS_BASE_URL}/api/events/dashboard`)

  source.addEventListener('dashboard_snapshot', (event) => {
    onSnapshot(JSON.parse((event as MessageEvent).data) as DashboardLiveSnapshot)
  })
  source.addEventListener('request_status', onPipelineEvent)
  source.addEventListener('prediction_result', onPipelineEvent)
  source.addEventListener('dead_letter', onPipelineEvent)
  source.onerror = onError

  return () => source.close()
}
