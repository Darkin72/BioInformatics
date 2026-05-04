import { apiRequest } from '../../shared/apiClient'
import type { LatestPrediction, ProteinRequestList } from '../../shared/types'

export function getLatestPrediction(proteinId: string) {
  return apiRequest<LatestPrediction | null>(
    `/api/proteins/${encodeURIComponent(proteinId)}/latest-prediction`,
  )
}

export function getProteinRequests(proteinId: string) {
  return apiRequest<ProteinRequestList>(
    `/api/proteins/${encodeURIComponent(proteinId)}/requests`,
  )
}
