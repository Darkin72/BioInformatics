import { useCallback, useEffect, useState } from 'react'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type {
  AdminRequestList,
  InferenceRequest,
  RequestStatus,
  RequestTimelineEvent,
} from '../../shared/types'
import { openDashboardEvents } from '../dashboard/dashboardApi'
import { deleteAdminRequest, getAdminRequests, getRequestTimeline } from './adminApi'

interface AdminRequestsPageProps {
  navigate: (path: string) => void
}

const statusOptions: Array<RequestStatus | ''> = [
  '',
  'processing',
  'completed',
  'failed',
  'retrying',
  'cancelled',
]

const tableOptions = [
  {
    label: 'By day',
    value: 'requests_by_day',
  },
  {
    label: 'By status',
    value: 'requests_by_status_window',
  },
  {
    label: 'By user',
    value: 'requests_by_user_window',
  },
]

export function AdminRequestsPage({ navigate }: AdminRequestsPageProps) {
  const [table, setTable] = useState('requests_by_day')
  const [status, setStatus] = useState('')
  const [username, setUsername] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [remote, setRemote] = useState<AdminRequestList | null>(null)
  const [timeline, setTimeline] = useState<RequestTimelineEvent[]>([])
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [deletingRequestId, setDeletingRequestId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const loadRequests = useCallback(async (showLoading = false) => {
    if (showLoading) {
      setIsLoading(true)
    }
    try {
      setRemote(
        await getAdminRequests({
          table,
          status,
          username: username.trim() || undefined,
          page,
          pageSize,
        }),
      )
      setError(null)
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load admin requests.',
      )
    } finally {
      if (showLoading) {
        setIsLoading(false)
      }
    }
  }, [table, status, username, page, pageSize])

  async function openTimeline(requestId: string) {
    setSelectedRequestId(requestId)
    setTimeline([])
    try {
      setTimeline(await getRequestTimeline(requestId))
    } catch {
      setTimeline([])
    }
  }

  async function deleteRequest(request: InferenceRequest) {
    const confirmed = window.confirm(
      `Delete request ${request.request_id} from Cassandra and in-memory history?`,
    )
    if (!confirmed) {
      return
    }

    setDeletingRequestId(request.request_id)
    try {
      await deleteAdminRequest(request)
      if (selectedRequestId === request.request_id) {
        setSelectedRequestId(null)
        setTimeline([])
      }
      await loadRequests(false)
      setError(null)
    } catch (deleteError) {
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : 'Unable to delete request.',
      )
    } finally {
      setDeletingRequestId(null)
    }
  }

  useEffect(() => {
    queueMicrotask(() => {
      void loadRequests(true)
    })
  }, [loadRequests])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadRequests(false)
    }, 5000)
    return () => window.clearInterval(intervalId)
  }, [loadRequests])

  useEffect(() => {
    const close = openDashboardEvents(
      () => undefined,
      () => {
        void loadRequests(false)
      },
      () => undefined,
    )
    return close
  }, [loadRequests])

  function updateTable(nextTable: string) {
    setTable(nextTable)
    setPage(1)
    if (nextTable === 'requests_by_status_window' && !status) {
      setStatus('completed')
    }
  }

  if (isLoading && !remote) {
    return <LoadingState />
  }

  if (error && !remote) {
    return <ErrorState message={error} />
  }

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>Admin request console</h2>
          <p>
            Source {remote?.source ?? '-'} | table {remote?.table ?? table} | page{' '}
            {remote?.page ?? page} | updated{' '}
            {remote ? formatDateTime(remote.updated_at) : '-'}
          </p>
        </div>
      </div>

      <section className="filter-panel">
        <label>
          Table
          <select value={table} onChange={(event) => updateTable(event.target.value)}>
            {tableOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value)
              setPage(1)
            }}
          >
            {statusOptions.map((option) => (
              <option key={option || 'all'} value={option}>
                {option || 'all'}
              </option>
            ))}
          </select>
        </label>
        <label>
          User
          <input
            placeholder="admin or username"
            value={username}
            onChange={(event) => {
              setUsername(event.target.value)
              setPage(1)
            }}
          />
        </label>
        <label>
          Page size
          <select
            value={pageSize}
            onChange={(event) => {
              setPageSize(Number(event.target.value))
              setPage(1)
            }}
          >
            {[10, 25, 50, 100].map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </section>

      {error ? <ErrorState message={error} /> : null}

      <div className="admin-grid">
        <section className="panel">
          <div className="section-header compact">
            <h2>All user requests</h2>
            <span>
              {remote?.returned ?? 0} rows | page {remote?.page ?? page}
            </span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Protein</th>
                  <th>Status</th>
                  <th>Stage</th>
                  <th>Created</th>
                  <th>Model</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {remote?.items.map((request) => (
                  <tr key={request.request_id}>
                    <td>
                      <button
                        className="table-link"
                        onClick={() => openTimeline(request.request_id)}
                        type="button"
                      >
                        {request.request_id}
                      </button>
                    </td>
                    <td>{request.protein_id}</td>
                    <td>
                      <StatusBadge status={request.current_status} />
                    </td>
                    <td>{request.stage_name ?? '-'}</td>
                    <td>{formatDateTime(request.created_at)}</td>
                    <td>{request.model_version ?? '-'}</td>
                    <td>
                      <button
                        className="danger-link"
                        disabled={deletingRequestId === request.request_id}
                        onClick={() => void deleteRequest(request)}
                        type="button"
                      >
                        {deletingRequestId === request.request_id ? 'Deleting...' : 'Delete'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="pagination-row">
            <button
              className="secondary-button"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              type="button"
            >
              Previous
            </button>
            <span>
              Page {remote?.page ?? page} | {remote?.returned ?? 0} rows
            </span>
            <button
              className="secondary-button"
              disabled={!remote?.has_next}
              onClick={() => setPage((current) => current + 1)}
              type="button"
            >
              Next
            </button>
          </div>
        </section>

        <section className="panel">
          <div className="section-header compact">
            <h2>Request timeline</h2>
            <button
              className="link-button"
              disabled={!selectedRequestId}
              onClick={() =>
                selectedRequestId ? navigate(`/requests/${selectedRequestId}`) : null
              }
              type="button"
            >
              Open request
            </button>
          </div>
          {selectedRequestId ? (
            <div className="timeline">
              {timeline.map((event) => (
                <div className="timeline-item" key={`${event.event_ts}-${event.event_type}`}>
                  <strong>{event.event_type || 'Timeline event'}</strong>
                  <span>{formatDateTime(event.event_ts)}</span>
                  <p>{event.stage_name ?? event.status ?? '-'}</p>
                  {event.message ? <small>{event.message}</small> : null}
                </div>
              ))}
              {!timeline.length ? (
                <p className="muted-copy">No Cassandra timeline rows yet.</p>
              ) : null}
            </div>
          ) : (
            <p className="muted-copy">Select a request to inspect stage history.</p>
          )}
        </section>
      </div>
    </section>
  )
}
