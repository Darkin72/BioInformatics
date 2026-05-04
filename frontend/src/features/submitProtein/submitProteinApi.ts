import { apiRequest } from '../../shared/apiClient'
import type {
  CreateInferenceRequestPayload,
  InferenceRequest,
} from '../../shared/types'

export function createInferenceRequest(payload: CreateInferenceRequestPayload) {
  return apiRequest<InferenceRequest>('/api/inference-requests', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
