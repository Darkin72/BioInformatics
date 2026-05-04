import { useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type { UserRequestList } from '../../shared/types'
import { getMyRequests } from './requestsApi'

interface MyRequestsPageProps {
  navigate: (path: string) => void
}

export function MyRequestsPage({ navigate }: MyRequestsPageProps) {
  const [days, setDays] = useState(30)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [remote, setRemote] = useState<UserRequestList | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true
    setIsLoading(true)

    getMyRequests({ days, page, pageSize })
      .then((data) => {
        if (isActive) {
          setRemote(data)
          setError(null)
        }
      })
      .catch((loadError: unknown) => {
        if (isActive) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load your requests.',
          )
        }
      })
      .finally(() => {
        if (isActive) {
          setIsLoading(false)
        }
      })

    return () => {
      isActive = false
    }
  }, [days, page, pageSize])

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
          <h2>My requests</h2>
          <p>
            {remote?.returned ?? 0} rows from {remote?.source ?? '-'} | updated{' '}
            {remote ? formatDateTime(remote.updated_at) : '-'}
          </p>
        </div>
      </div>

      <section className="filter-panel user-filter-panel">
        <label>
          Days
          <select
            value={days}
            onChange={(event) => {
              setDays(Number(event.target.value))
              setPage(1)
            }}
          >
            {[7, 30, 90, 365].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
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

      {remote && remote.items.length === 0 ? (
        <EmptyState message="You do not have any requests in this window." />
      ) : null}

      {remote && remote.items.length > 0 ? (
        <section className="panel">
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Protein</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {remote.items.map((request) => (
                  <tr key={request.request_id}>
                    <td className="mono">{request.request_id}</td>
                    <td>{request.protein_id}</td>
                    <td>
                      <StatusBadge status={request.current_status} />
                    </td>
                    <td>{formatDateTime(request.updated_at ?? request.created_at)}</td>
                    <td>
                      <button
                        className="table-link"
                        onClick={() => navigate(`/requests/${request.request_id}`)}
                        type="button"
                      >
                        Open
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
              Page {remote.page} | {remote.returned} rows
            </span>
            <button
              className="secondary-button"
              disabled={!remote.has_next}
              onClick={() => setPage((current) => current + 1)}
              type="button"
            >
              Next
            </button>
          </div>
        </section>
      ) : null}
    </section>
  )
}
