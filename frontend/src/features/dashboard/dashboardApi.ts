import { apiRequest, isMockApi } from '../../shared/apiClient'
import { mockGetDashboardSummary } from '../../shared/mockApi'
import type { DashboardSummary } from '../../shared/types'

export function getDashboardSummary() {
  if (isMockApi) {
    return mockGetDashboardSummary()
  }

  return apiRequest<DashboardSummary>(
    '/api/metrics/pipeline/summary?window=minute',
  )
}
