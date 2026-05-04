import { apiRequest } from '../../shared/apiClient'
import type { DashboardSummary } from '../../shared/types'

export function getDashboardSummary() {
  return apiRequest<DashboardSummary>(
    '/api/metrics/pipeline/summary?window=minute',
  )
}
