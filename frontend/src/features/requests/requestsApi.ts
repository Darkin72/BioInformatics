import { apiRequest, isMockApi } from '../../shared/apiClient'
import { mockGetRequestStatus } from '../../shared/mockApi'
import type { InferenceRequest } from '../../shared/types'

export function getRequestStatus(requestId: string) {
  if (isMockApi) {
    return mockGetRequestStatus(requestId)
  }

  return apiRequest<InferenceRequest>(
    `/api/inference-requests/${encodeURIComponent(requestId)}`,
  )
}
