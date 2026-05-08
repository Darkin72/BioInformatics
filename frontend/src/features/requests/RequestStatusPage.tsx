import { useCallback, useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type { RequestResult } from '../../shared/types'
import {
  getRequestResult,
  openRequestEvents,
  type RequestStreamEvent,
} from './requestsApi'

interface RequestStatusPageProps {
  requestId: string
  isAdmin: boolean
  navigate: (path: string) => void
}

type CollapsibleSectionKey = 'input' | 'prediction' | 'metadata'

const pollingStatuses = new Set(['pending', 'processing', 'retrying'])

function formatScore(score: number) {
  return `${(score * 100).toFixed(1)}%`
}

function formatOntology(ontology?: string | null) {
  const normalized = ontology?.toUpperCase()
  if (normalized === 'MF' || normalized === 'MFO' || normalized === 'F') {
    return 'Molecular Function'
  }
  if (normalized === 'BP' || normalized === 'BPO' || normalized === 'P') {
    return 'Biological Process'
  }
  if (normalized === 'CC' || normalized === 'CCO' || normalized === 'C') {
    return 'Cellular Component'
  }
  return ontology ?? '-'
}

function CollapseButton({
  isOpen,
  label,
  onToggle,
}: {
  isOpen: boolean
  label: string
  onToggle: () => void
}) {
  return (
    <button
      aria-expanded={isOpen}
      className="collapse-toggle"
      onClick={onToggle}
      type="button"
    >
      <span>{isOpen ? 'Collapse' : 'Expand'}</span>
      <svg aria-hidden="true" className="ui-icon" viewBox="0 0 24 24">
        <path d={isOpen ? 'M6 15l6-6 6 6' : 'M6 9l6 6 6-6'} />
      </svg>
      <span className="sr-only">{label}</span>
    </button>
  )
}

export function RequestStatusPage({
  isAdmin,
  requestId,
  navigate,
}: RequestStatusPageProps) {
  const [streamEvents, setStreamEvents] = useState<RequestStreamEvent[]>([])
  const [openSections, setOpenSections] = useState<
    Record<CollapsibleSectionKey, boolean>
  >({
    input: true,
    metadata: true,
    prediction: true,
  })
  const [remoteState, setRemoteState] = useState<{
    requestId: string
    result: RequestResult | null
    error: string | null
  }>({
    requestId: '',
    result: null,
    error: null,
  })

  const loadRequestResult = useCallback(() => {
    return getRequestResult(requestId)
      .then((data) => {
        setRemoteState({
          requestId,
          result: data,
          error: null,
        })
      })
      .catch((loadError: unknown) => {
        setRemoteState({
          requestId,
          result: null,
          error:
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load request status.',
        })
      })
  }, [requestId])

  useEffect(() => {
    let isActive = true

    setRemoteState({ requestId: '', result: null, error: null })
    setStreamEvents([])

    loadRequestResult()
      .catch(() => {
        // The error state is written by loadRequestResult.
      })
      .finally(() => {
        if (!isActive) {
          return
        }
      })

    return () => {
      isActive = false
    }
  }, [loadRequestResult, requestId])

  const result =
    remoteState.requestId === requestId ? remoteState.result : null
  const request = result?.request ?? null
  const error = remoteState.requestId === requestId ? remoteState.error : null
  const isLoading = remoteState.requestId !== requestId

  useEffect(() => {
    if (!request || !pollingStatuses.has(request.current_status)) {
      return
    }

    const intervalId = window.setInterval(() => {
      void loadRequestResult()
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [loadRequestResult, request])

  useEffect(() => {
    const close = openRequestEvents(
      requestId,
      (event) => {
        setStreamEvents((events) => [event, ...events].slice(0, 8))
        void loadRequestResult()
      },
      () => undefined,
      () => undefined,
    )

    return close
  }, [loadRequestResult, requestId])

  if (isLoading) {
    return <LoadingState />
  }

  if (error) {
    return <ErrorState message={error} />
  }

  if (!request) {
    return <EmptyState message="Request not found." />
  }

  const prediction = result?.prediction ?? null
  const requestInput = result?.input ?? null
  const topTerm = prediction?.top_terms[0] ?? null
  const predictedAt = prediction?.predicted_at
    ? formatDateTime(prediction.predicted_at)
    : null
  const isAwaitingPrediction = pollingStatuses.has(request.current_status)

  function toggleSection(section: CollapsibleSectionKey) {
    setOpenSections((current) => ({
      ...current,
      [section]: !current[section],
    }))
  }

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>Request result</h2>
          <p className="mono">{request.request_id}</p>
        </div>
        <StatusBadge status={request.current_status} />
      </div>

      {streamEvents.length ? (
        <section className="panel request-stream-panel">
          <div className="request-stream-track">
            {streamEvents.map((event) => (
              <div
                className="request-stream-event"
                key={`${event.eventType}-${event.receivedAt}`}
              >
                <span>{event.eventType}</span>
                <strong>
                  {String(
                    event.payload.stage_name ??
                      event.payload.current_status ??
                      event.payload.status ??
                      'event received',
                  )}
                </strong>
                <small>{formatDateTime(event.receivedAt)}</small>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header compact">
          <h2>Input sequence</h2>
          <div className="section-header-actions">
            {requestInput?.sequence_length ? (
              <span>{requestInput.sequence_length} amino acids</span>
            ) : null}
            <CollapseButton
              isOpen={openSections.input}
              label="Input sequence"
              onToggle={() => toggleSection('input')}
            />
          </div>
        </div>

        {openSections.input ? requestInput ? (
          <div className="input-result">
            <dl className="prediction-summary">
              <div>
                <dt>Protein</dt>
                <dd>{requestInput.protein_id}</dd>
              </div>
              <div>
                <dt>Length</dt>
                <dd>{requestInput.sequence_length ?? '-'}</dd>
              </div>
              {isAdmin ? (
                <div>
                  <dt>Source</dt>
                  <dd>{requestInput.source ?? request.source ?? '-'}</dd>
                </div>
              ) : null}
              {isAdmin ? (
                <div>
                  <dt>Metadata</dt>
                  <dd>
                    {requestInput.metadata
                      ? JSON.stringify(requestInput.metadata)
                      : '-'}
                  </dd>
                </div>
              ) : null}
            </dl>
            {requestInput.sequence ? (
              <pre className="sequence-view">{requestInput.sequence}</pre>
            ) : (
              <EmptyState message="Input sequence was not stored for this request." />
            )}
          </div>
        ) : (
          <EmptyState message="Input was not stored for this request." />
        ) : null}
      </section>

      <section className="panel">
        <div className="section-header compact">
          <h2>Prediction result</h2>
          <div className="section-header-actions">
            {predictedAt ? <span>{predictedAt}</span> : null}
            <CollapseButton
              isOpen={openSections.prediction}
              label="Prediction result"
              onToggle={() => toggleSection('prediction')}
            />
          </div>
        </div>

        {openSections.prediction ? (
          <>
            {prediction && topTerm ? (
              <div className="prediction-result">
                <div className="prediction-highlight">
                  <div>
                    <span>Top GO term</span>
                    <strong>{topTerm.term_id}</strong>
                    <p>{topTerm.term_name ?? 'Unnamed ontology term'}</p>
                  </div>
                </div>

                <dl className="prediction-summary">
                  <div>
                    <dt>Protein</dt>
                    <dd>{prediction.protein_id}</dd>
                  </div>
                  <div>
                    <dt>Ontology</dt>
                    <dd>{formatOntology(topTerm.ontology)}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{prediction.model_version}</dd>
                  </div>
                  <div>
                    <dt>Terms returned</dt>
                    <dd>{prediction.top_terms.length}</dd>
                  </div>
                </dl>

                {prediction.confidence_summary ? (
                  <p className="result-summary">{prediction.confidence_summary}</p>
                ) : null}
              </div>
            ) : request.current_status === 'completed' ? (
              <EmptyState message="No prediction result is available for this request." />
            ) : isAwaitingPrediction ? (
              <div className="prediction-processing">
                <div className="prediction-processing-header">
                  <span className="processing-dot" />
                  <strong>{request.current_status}</strong>
                </div>
                <p>
                  Prediction is running
                  {request.stage_name ? `: ${request.stage_name}` : '.'}
                </p>
                <div
                  aria-label="Prediction is processing"
                  className="processing-progress"
                  role="progressbar"
                >
                  <div />
                </div>
              </div>
            ) : (
              <EmptyState message="The server has not returned a result for this request yet." />
            )}

            {prediction?.top_terms.length ? (
              <div className="label-result-grid">
                {prediction.top_terms.map((term, index) => {
                  const labelScorePercent = Math.max(
                    0,
                    Math.min(100, term.score * 100),
                  )

                  return (
                    <section
                      className="label-result-card"
                      key={`${term.term_id}-${term.ontology ?? ''}-${index}`}
                    >
                      <div className="label-result-header">
                        <span>Term {index + 1}</span>
                        <strong>{formatScore(term.score)}</strong>
                      </div>
                      <div>
                        <h3>{term.term_name ?? 'Unnamed ontology term'}</h3>
                        <p className="mono">{term.term_id}</p>
                      </div>
                      {term.definition ? (
                        <p className="term-definition">{term.definition}</p>
                      ) : null}
                      <dl className="label-result-details">
                        <div>
                          <dt>Ontology</dt>
                          <dd>{formatOntology(term.ontology)}</dd>
                        </div>
                        <div>
                          <dt>Confidence</dt>
                          <dd>{formatScore(term.score)}</dd>
                        </div>
                      </dl>
                      <div className="score-track">
                        <div style={{ width: `${labelScorePercent}%` }} />
                      </div>
                    </section>
                  )
                })}
              </div>
            ) : null}
          </>
        ) : null}
      </section>

      <section className="panel">
        <div className="section-header compact">
          <h2>Request metadata</h2>
          <CollapseButton
            isOpen={openSections.metadata}
            label="Request metadata"
            onToggle={() => toggleSection('metadata')}
          />
        </div>
        {openSections.metadata ? (
          <>
            <dl className="detail-grid">
              <div>
                <dt>Protein ID</dt>
                <dd>{request.protein_id}</dd>
              </div>
              <div>
                <dt>Stage</dt>
                <dd>{request.stage_name ?? '-'}</dd>
              </div>
              <div>
                <dt>Created</dt>
                <dd>{formatDateTime(request.created_at)}</dd>
              </div>
              <div>
                <dt>Updated</dt>
                <dd>{formatDateTime(request.updated_at)}</dd>
              </div>
              <div>
                <dt>Model version</dt>
                <dd>{request.model_version ?? '-'}</dd>
              </div>
              <div>
                <dt>Feature version</dt>
                <dd>{request.feature_version ?? '-'}</dd>
              </div>
              <div>
                <dt>Retry count</dt>
                <dd>{request.retry_count ?? 0}</dd>
              </div>
              <div>
                <dt>Error</dt>
                <dd>{request.error_code ?? '-'}</dd>
              </div>
            </dl>

            {request.error_message ? (
              <ErrorState message={request.error_message} />
            ) : null}

            <div className="actions-row">
              <button
                className="secondary-button"
                onClick={() => navigate('/my/requests')}
                type="button"
              >
                Back to my requests
              </button>
              <button
                className="secondary-button"
                onClick={() => navigate(`/proteins/${request.protein_id}/latest`)}
                type="button"
              >
                Open protein requests
              </button>
            </div>
          </>
        ) : null}
      </section>
    </section>
  )
}
