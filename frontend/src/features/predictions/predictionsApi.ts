import { apiRequest } from '../../shared/apiClient'
import type { LatestPrediction } from '../../shared/types'

export function getLatestPrediction(proteinId: string) {
  return apiRequest<LatestPrediction | null>(
    `/api/proteins/${encodeURIComponent(proteinId)}/latest-prediction`,
  )
}
