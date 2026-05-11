import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type { ProteinRequestList } from '../../shared/types'
import { getProteinRequests } from './predictionsApi'

interface LatestPredictionPageProps {
  proteinId?: string
  navigate: (path: string) => void
}

export function LatestPredictionPage({
  proteinId,
  navigate,
}: LatestPredictionPageProps) {
  const [searchValue, setSearchValue] = useState(proteinId ?? 'P12345')
  const [remoteState, setRemoteState] = useState<{
    proteinId: string
    result: ProteinRequestList | null
    error: string | null
  }>({
    proteinId: '',
    result: null,
    error: null,
  })
  const [hasSearched, setHasSearched] = useState(Boolean(proteinId))

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const id = searchValue.trim()

    if (!id) {
      setRemoteState({
        proteinId: '',
        result: null,
        error: 'Protein ID is required.',
      })
      return
    }

    navigate(`/proteins/${encodeURIComponent(id)}/latest`)
  }

  useEffect(() => {
    if (!proteinId) {
      return
    }

    let isActive = true

    getProteinRequests(proteinId)
      .then((data) => {
        if (isActive) {
          setRemoteState({
            proteinId,
            result: data,
            error: null,
          })
          setHasSearched(true)
        }
      })
      .catch((loadError: unknown) => {
        if (isActive) {
          setRemoteState({
            proteinId,
            result: null,
            error:
              loadError instanceof Error
                ? loadError.message
                : 'Unable to load protein requests.',
          })
        }
      })

    return () => {
      isActive = false
    }
  }, [proteinId])

  const result =
    proteinId && remoteState.proteinId === proteinId ? remoteState.result : null
  const error =
    !proteinId || remoteState.proteinId === proteinId ? remoteState.error : null
  const isLoading = Boolean(
    proteinId && remoteState.proteinId !== proteinId && !error,
  )

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>Protein requests</h2>
          <p>Search request history by protein ID.</p>
        </div>
      </div>

      <form className="search-panel" onSubmit={handleSearch}>
        <label>
          Protein ID
          <input
            onChange={(event) => setSearchValue(event.target.value)}
            placeholder="P12345"
            value={searchValue}
          />
        </label>
        <button className="primary-button" type="submit">
          Search
        </button>
      </form>

      {isLoading ? <LoadingState /> : null}
      {error ? <ErrorState message={error} /> : null}
      {!isLoading && !error && hasSearched && result?.items.length === 0 ? (
        <EmptyState message="No requests found for this protein." />
      ) : null}

      {!isLoading && result && result.items.length > 0 ? (
        <section className="panel">
          <div className="section-header compact">
            <div>
              <h2>{result.protein_id}</h2>
              <p>
                {result.returned} request{result.returned === 1 ? '' : 's'} found
                from {result.source}.
              </p>
            </div>
            <span>{formatDateTime(result.updated_at)}</span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>User</th>
                  <th>Status</th>
                  <th>Stage</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {result.items.map((request) => (
                  <tr key={request.request_id}>
                    <td>
                      <button
                        className="table-link"
                        onClick={() => navigate(`/requests/${request.request_id}`)}
                        type="button"
                      >
                        {request.request_id}
                      </button>
                    </td>
                    <td>{request.username ?? '-'}</td>
                    <td>
                      <StatusBadge status={request.current_status} />
                    </td>
                    <td>{request.stage_name ?? '-'}</td>
                    <td>{formatDateTime(request.updated_at ?? request.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </section>
  )
}
