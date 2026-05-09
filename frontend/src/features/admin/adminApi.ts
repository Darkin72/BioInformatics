import { API_BASE_URL, apiRequest, getAccessToken } from '../../shared/apiClient'
import type {
  AdminRequestList,
  AdminUserList,
  InferenceRequest,
  RequestTimelineEvent,
  RetryRequestResponse,
} from '../../shared/types'

export function getAdminRequests(params: {
  table?: string
  status?: string
  username?: string
  page?: number
  pageSize?: number
}) {
  const search = new URLSearchParams()
  if (params.table) {
    search.set('table', params.table)
  }
  if (params.status) {
    search.set('status', params.status)
  }
  if (params.username) {
    search.set('username', params.username)
  }
  search.set('page', String(params.page ?? 1))
  search.set('page_size', String(params.pageSize ?? 25))
  return apiRequest<AdminRequestList>(`/api/admin/requests?${search}`)
}

export function clearRequestHistory() {
  return apiRequest<{
    status: string
    truncated_tables: string[]
    cleared_memory_items: number
    updated_at: string
  }>('/api/admin/request-history', {
    method: 'DELETE',
  })
}

export function deleteAdminRequest(request: InferenceRequest) {
  const search = new URLSearchParams()
  search.set('protein_id', request.protein_id)
  search.set('created_at', request.created_at)
  search.set('current_status', request.current_status)
  if (request.username) {
    search.set('username', request.username)
  }
  if (request.source) {
    search.set('source', request.source)
  }
  if (request.updated_at) {
    search.set('updated_at', request.updated_at)
  }
  if (request.stage_name) {
    search.set('stage_name', request.stage_name)
  }
  if (request.model_version) {
    search.set('model_version', request.model_version)
  }
  if (request.feature_version) {
    search.set('feature_version', request.feature_version)
  }

  return apiRequest<{
    status: string
    request_id: string
    deleted_tables: string[]
    cleared_memory_items: number
    updated_at: string
  }>(
    `/api/admin/requests/${encodeURIComponent(request.request_id)}?${search}`,
    {
      method: 'DELETE',
    },
  )
}

export function retryAdminRequest(requestId: string) {
  return apiRequest<RetryRequestResponse>(
    `/api/inference-requests/${encodeURIComponent(requestId)}/retry`,
    {
      method: 'POST',
    },
  )
}

export function getRequestTimeline(requestId: string) {
  return apiRequest<RequestTimelineEvent[]>(
    `/api/admin/requests/${encodeURIComponent(requestId)}/timeline`,
  )
}

export function getAdminUsers() {
  return apiRequest<AdminUserList>('/api/admin/users')
}

export function deleteAdminUser(username: string) {
  return apiRequest<AdminUserList>(
    `/api/admin/users/${encodeURIComponent(username)}`,
    {
      method: 'DELETE',
    },
  )
}

export function openAdminUsersEvents(
  onUsers: (users: AdminUserList) => void,
  onError: () => void,
) {
  const token = getAccessToken()
  if (!token) {
    onError()
    return () => undefined
  }

  const search = new URLSearchParams({ token })
  const source = new EventSource(
    `${API_BASE_URL}/api/admin/users/events?${search}`,
  )

  source.addEventListener('admin_users', (event) => {
    onUsers(JSON.parse((event as MessageEvent).data) as AdminUserList)
  })
  source.onerror = onError

  return () => source.close()
}
