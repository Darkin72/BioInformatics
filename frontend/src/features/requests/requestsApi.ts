import { apiRequest } from '../../shared/apiClient'
import type { InferenceRequest } from '../../shared/types'

export function getRequestStatus(requestId: string) {
  return apiRequest<InferenceRequest>(
    `/api/inference-requests/${encodeURIComponent(requestId)}`,
  )
}
