import { API_BASE_URL, apiRequest, getAccessToken } from '../../shared/apiClient'
import type {
  AdminRequestList,
  AdminUserList,
  RequestTimelineEvent,
} from '../../shared/types'

export function getAdminRequests(params: {
  table?: string
  status?: string
  username?: string
  requestDate?: string
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
  if (params.requestDate) {
    search.set('request_date', params.requestDate)
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
