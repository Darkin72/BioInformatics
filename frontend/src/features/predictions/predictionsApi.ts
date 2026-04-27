import { apiRequest, isMockApi } from '../../shared/apiClient'
import { mockGetLatestPrediction } from '../../shared/mockApi'
import type { LatestPrediction } from '../../shared/types'

export function getLatestPrediction(proteinId: string) {
  if (isMockApi) {
    return mockGetLatestPrediction(proteinId)
  }

  return apiRequest<LatestPrediction | null>(
    `/api/proteins/${encodeURIComponent(proteinId)}/latest-prediction`,
  )
}
