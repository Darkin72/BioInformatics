import { apiRequest, isMockApi } from '../../shared/apiClient'
import { mockCreateInferenceRequest } from '../../shared/mockApi'
import type {
  CreateInferenceRequestPayload,
  InferenceRequest,
} from '../../shared/types'

export function createInferenceRequest(payload: CreateInferenceRequestPayload) {
  if (isMockApi) {
    return mockCreateInferenceRequest(payload)
  }

  return apiRequest<InferenceRequest>('/api/inference-requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
