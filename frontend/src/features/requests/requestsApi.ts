import { EVENTS_BASE_URL, apiRequest } from '../../shared/apiClient'
import type {
  InferenceRequest,
  LatestPrediction,
  RequestResult,
  UserRequestList,
} from '../../shared/types'

export interface RequestStreamEvent {
  eventType: string
  payload: Record<string, unknown>
  receivedAt: string
}

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

export function getRequestProteinResult(requestId: string, proteinId: string) {
  return apiRequest<LatestPrediction>(
    `/api/inference-requests/${encodeURIComponent(requestId)}/proteins/${encodeURIComponent(
      proteinId,
    )}/result`,
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

function parseEventPayload(event: Event) {
  const message = event as MessageEvent
  return JSON.parse(message.data) as Record<string, unknown>
}

export function openRequestEvents(
  requestId: string,
  onRequestEvent: (event: RequestStreamEvent) => void,
  onOpen: () => void,
  onError: () => void,
) {
  const source = new EventSource(`${EVENTS_BASE_URL}/api/events/dashboard`)
  const eventTypes = ['request_status', 'prediction_result', 'dead_letter']

  function handleEvent(eventType: string) {
    return (event: Event) => {
      const payload = parseEventPayload(event)
      if (String(payload.request_id ?? '') !== requestId) {
        return
      }

      onRequestEvent({
        eventType,
        payload,
        receivedAt: new Date().toISOString(),
      })
    }
  }

  const handlers = eventTypes.map((eventType) => {
    const handler = handleEvent(eventType)
    source.addEventListener(eventType, handler)
    return { eventType, handler }
  })

  source.onopen = onOpen
  source.onerror = onError

  return () => {
    handlers.forEach(({ eventType, handler }) => {
      source.removeEventListener(eventType, handler)
    })
    source.close()
  }
}
