import { apiRequest } from '../../shared/apiClient'
import type { InferenceRequest, RequestResult, UserRequestList } from '../../shared/types'

export function getRequestStatus(requestId: string) {
  return apiRequest<InferenceRequest>(
    `/api/inference-requests/${encodeURIComponent(requestId)}`,
  )
}

export function getRequestResult(requestId: string) {
  return apiRequest<RequestResult>(
    `/api/inference-requests/${encodeURIComponent(requestId)}/result`,
  )
}

export function getMyRequests(params: {
  days?: number
  page?: number
  pageSize?: number
} = {}) {
  const search = new URLSearchParams()
  search.set('days', String(params.days ?? 30))
  search.set('page', String(params.page ?? 1))
  search.set('page_size', String(params.pageSize ?? 25))
  return apiRequest<UserRequestList>(`/api/my/requests?${search}`)
}
