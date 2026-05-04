import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { formatDateTime } from '../../shared/date'
import { formatScore } from '../../shared/format'
import type { LatestPrediction } from '../../shared/types'
import { getLatestPrediction } from './predictionsApi'

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
    prediction: LatestPrediction | null
    error: string | null
  }>({
    proteinId: '',
    prediction: null,
    error: null,
  })
  const [hasSearched, setHasSearched] = useState(Boolean(proteinId))

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const id = searchValue.trim()

    if (!id) {
      setRemoteState({
        proteinId: '',
        prediction: null,
        error: 'Protein ID is required.',
      })
      return
    }

    navigate(`/proteins/${encodeURIComponent(id)}/latest`)
  }

  useEffect(() => {
    if (proteinId) {
      let isActive = true

      getLatestPrediction(proteinId)
        .then((data) => {
          if (isActive) {
            setRemoteState({
              proteinId,
              prediction: data,
              error: null,
            })
            setHasSearched(true)
          }
        })
        .catch((loadError: unknown) => {
          if (isActive) {
            setRemoteState({
              proteinId,
              prediction: null,
              error:
                loadError instanceof Error
                  ? loadError.message
                  : 'Unable to load latest prediction.',
            })
          }
        })

      return () => {
        isActive = false
      }
    }
  }, [proteinId])

  const prediction =
    proteinId && remoteState.proteinId === proteinId
      ? remoteState.prediction
      : null
  const error =
    !proteinId || remoteState.proteinId === proteinId
      ? remoteState.error
      : null
  const isLoading = Boolean(
    proteinId && remoteState.proteinId !== proteinId && !error,
  )

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>Latest prediction</h2>
          <p>Search the serving store by protein ID.</p>
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
      {!isLoading && !error && hasSearched && !prediction ? (
        <EmptyState message="No prediction found for this protein." />
      ) : null}

      {!isLoading && prediction ? (
        <section className="panel">
          <div className="section-header compact">
            <div>
              <h2>{prediction.protein_id}</h2>
              <p>{prediction.confidence_summary ?? 'No summary available.'}</p>
            </div>
            <span className="mono">{prediction.model_version}</span>
          </div>

          <dl className="detail-grid compact-details">
            <div>
              <dt>Request ID</dt>
              <dd>{prediction.request_id}</dd>
            </div>
            <div>
              <dt>Predicted</dt>
              <dd>{formatDateTime(prediction.predicted_at)}</dd>
            </div>
          </dl>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>GO term</th>
                  <th>Name</th>
                  <th>Ontology</th>
                  <th>Score</th>
                </tr>
              </thead>
              <tbody>
                {[...prediction.top_terms]
                  .sort((left, right) => right.score - left.score)
                  .map((term) => (
                    <tr key={term.term_id}>
                      <td className="mono">{term.term_id}</td>
                      <td>{term.term_name ?? '-'}</td>
                      <td>{term.ontology ?? '-'}</td>
                      <td>{formatScore(term.score)}</td>
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
