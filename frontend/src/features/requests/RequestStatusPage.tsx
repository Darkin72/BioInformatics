import { useCallback, useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type { PredictionTerm, RequestResult } from '../../shared/types'
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
const modalStepOrder = [
  'normalize_input',
  'batch_started',
  'extract_esm_embeddings',
  'run_esm_mlp',
  'encode_sequence_tensor',
  'run_protcnn',
  'run_bilstm',
  'select_model_output',
  'combine_ensemble',
  'postprocess_predictions',
]

const modalStepLabels: Record<string, string> = {
  batch_started: 'Batch queued',
  combine_ensemble: 'Combine ensemble',
  encode_sequence_tensor: 'Encode sequence',
  extract_esm_embeddings: 'ESM embeddings',
  normalize_input: 'Normalize input',
  postprocess_predictions: 'Postprocess terms',
  run_bilstm: 'BiLSTM branch',
  run_esm_mlp: 'ESM MLP branch',
  run_protcnn: 'ProtCNN branch',
  select_model_output: 'Select output',
}

const modalStepDescriptions: Record<string, string> = {
  batch_started: 'Open the next streamed batch.',
  combine_ensemble: 'Blend branch probabilities by configured weights.',
  encode_sequence_tensor: 'Encode amino acids for sequence models.',
  extract_esm_embeddings: 'Generate ESM representation vectors.',
  normalize_input: 'Validate and normalize protein records.',
  postprocess_predictions: 'Filter GO terms and attach metadata.',
  run_bilstm: 'Score with the BiLSTM attention branch.',
  run_esm_mlp: 'Score ESM embeddings with the MLP head.',
  run_protcnn: 'Score with the ProtCNN branch.',
  select_model_output: 'Use the requested single-model output.',
}

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

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function formatModalLabel(value: unknown) {
  const raw = String(value ?? '').replace(/^modal_/, '')
  if (!raw) {
    return 'Stream update'
  }
  return modalStepLabels[raw] ?? raw.replaceAll('_', ' ')
}

function getModalEvent(event: RequestStreamEvent) {
  return String(event.payload.modal_event ?? event.eventType)
}

function getModalData(event: RequestStreamEvent) {
  return asRecord(event.payload.modal_data)
}

function getModalStep(event: RequestStreamEvent) {
  return String(event.payload.modal_step ?? getModalData(event).step ?? '')
}

function stepsForModel(modelName: string) {
  const normalized = modelName.replace(/^cafa6-modal-/, '').toLowerCase()
  if (normalized === 'esm_mlp') {
    return [
      'normalize_input',
      'batch_started',
      'extract_esm_embeddings',
      'run_esm_mlp',
      'select_model_output',
      'postprocess_predictions',
    ]
  }
  if (normalized === 'protcnn') {
    return [
      'normalize_input',
      'batch_started',
      'encode_sequence_tensor',
      'run_protcnn',
      'select_model_output',
      'postprocess_predictions',
    ]
  }
  if (normalized === 'bilstm') {
    return [
      'normalize_input',
      'batch_started',
      'encode_sequence_tensor',
      'run_bilstm',
      'select_model_output',
      'postprocess_predictions',
    ]
  }
  return modalStepOrder.filter((step) => step !== 'select_model_output')
}

function mergeRequestEvents(
  current: RequestStreamEvent[],
  incoming: RequestStreamEvent[] = [],
) {
  const byKey = new Map<string, RequestStreamEvent>()
  ;[...current, ...incoming].forEach((event) => {
    byKey.set(
      `${event.eventType}-${event.receivedAt}-${String(event.payload.modal_event ?? '')}-${String(event.payload.modal_step ?? '')}`,
      event,
    )
  })
  return [...byKey.values()]
    .sort(
      (left, right) =>
        Date.parse(right.receivedAt) - Date.parse(left.receivedAt),
    )
    .slice(0, 80)
}

function buildStreamMonitor(events: RequestStreamEvent[]) {
  const chronological = [...events].sort(
    (left, right) => Date.parse(left.receivedAt) - Date.parse(right.receivedAt),
  )
  const progressEvents = chronological.filter((event) => getModalEvent(event) === 'progress')
  const seenSteps = new Set(
    progressEvents
      .map((event) => getModalStep(event))
      .filter(Boolean),
  )
  const doneEvent = chronological.find((event) => getModalEvent(event) === 'done')
  const hasPrediction = chronological.some((event) => event.eventType === 'prediction_result')
  const streamFinished = Boolean(doneEvent || hasPrediction)
  const completedSteps = new Set(
    progressEvents
      .filter((event, index) => {
        const status = String(event.payload.modal_step_status ?? getModalData(event).status)
        const step = getModalStep(event)
        return (
          status === 'done' ||
          (step === 'batch_started' && (streamFinished || progressEvents.length > index + 1))
        )
      })
      .map((event) => getModalStep(event))
      .filter(Boolean),
  )
  const latestProgress = progressEvents.at(-1) ?? null
  const activeStep = latestProgress ? getModalStep(latestProgress) : ''
  const latest = chronological.at(-1) ?? null
  const latestData = latest ? getModalData(latest) : {}
  const latestBatch = chronological
    .filter((event) => getModalEvent(event) === 'batch')
    .at(-1)
  const batchData = latestBatch ? getModalData(latestBatch) : {}
  const startEvent = chronological.find((event) => getModalEvent(event) === 'start')
  const startData = startEvent ? getModalData(startEvent) : {}
  const modelRecord = asRecord(batchData.model)
  const modelName = String(
    modelRecord.name ?? latestData.model ?? startData.model ?? 'ensemble',
  )
  const displaySteps = stepsForModel(modelName)
  const knownStepCount = displaySteps.filter((step) => completedSteps.has(step)).length
  const dynamicStepCount = completedSteps.size
  const progressBase = displaySteps.length
    ? (knownStepCount / displaySteps.length) * 86
    : 0
  const progressPercent = doneEvent || hasPrediction
    ? 100
    : Math.max(8, Math.min(92, progressBase || dynamicStepCount * 9))
  const totalRecords = Number(
    latestData.total_records ?? batchData.total_records ?? startData.total_input_records ?? 1,
  )
  const totalBatches = Number(
    latestData.total_batches ?? batchData.total_batches ?? 1,
  )
  const batchIndex = Number(
    latestData.batch_index ?? batchData.batch_index ?? 0,
  )

  return {
    activeLabel: latest
      ? formatModalLabel(getModalStep(latest) || latest.payload.stage_name || getModalEvent(latest))
      : 'Waiting for stream',
    activeStep,
    batchLabel: `${Math.min(batchIndex + 1, totalBatches)} / ${totalBatches}`,
    completedSteps,
    displaySteps,
    events: chronological.slice(-12).reverse(),
    modelName,
    progressPercent,
    seenSteps,
    streamFinished,
    totalRecords: Number.isFinite(totalRecords) ? totalRecords : 1,
  }
}

function mapPredictionRow(row: Record<string, unknown>): PredictionTerm | null {
  const termId = String(row.go_term ?? row.term_id ?? '').trim()
  if (!termId) {
    return null
  }

  return {
    term_id: termId,
    term_name: typeof row.name === 'string'
      ? row.name
      : typeof row.term_name === 'string'
        ? row.term_name
        : undefined,
    ontology: typeof row.aspect === 'string'
      ? (row.aspect as PredictionTerm['ontology'])
      : typeof row.ontology === 'string'
        ? (row.ontology as PredictionTerm['ontology'])
        : undefined,
    score: Number(row.score ?? 0),
  }
}

function termsFromRows(rows: unknown, proteinId?: string) {
  if (!Array.isArray(rows)) {
    return []
  }

  return rows
    .filter((row): row is Record<string, unknown> => Boolean(row) && typeof row === 'object')
    .filter((row) => !proteinId || !row.protein_id || String(row.protein_id) === proteinId)
    .map(mapPredictionRow)
    .filter((term): term is PredictionTerm => Boolean(term))
    .sort((left, right) => right.score - left.score)
}

function buildSolutionResults(prediction: RequestResult['prediction']) {
  if (!prediction) {
    return []
  }

  const serverResult = asRecord(prediction.server_result)
  const model = asRecord(serverResult.model)
  const weights = asRecord(model.weights)
  const branchPredictions = asRecord(serverResult.branch_predictions)
  const primaryLabel = String(
    model.name ?? prediction.model_version.replace(/^cafa6-modal-/, '') ?? 'ensemble',
  )
  const solutions: Array<{
    label: string
    role: string
    terms: PredictionTerm[]
    weight?: number
  }> = [
    {
      label: primaryLabel,
      role: 'Primary solution',
      terms: prediction.top_terms,
      weight: undefined,
    },
  ]

  Object.entries(branchPredictions).forEach(([branch, rows]) => {
    solutions.push({
      label: branch,
      role: 'Branch solution',
      terms: termsFromRows(rows, prediction.protein_id),
      weight: typeof weights[branch] === 'number' ? Number(weights[branch]) : undefined,
    })
  })

  return solutions
}

function progressFromStage(stageName?: string | null) {
  const normalized = String(stageName ?? '').replace(/^modal_/, '')
  if (normalized === 'accepted') {
    return 4
  }
  if (normalized === 'connecting') {
    return 7
  }
  if (normalized === 'stream_started') {
    return 12
  }
  if (normalized === 'stream_done') {
    return 96
  }

  const stepIndex = modalStepOrder.indexOf(normalized)
  if (stepIndex >= 0) {
    return Math.round(14 + ((stepIndex + 1) / modalStepOrder.length) * 72)
  }

  if (normalized.startsWith('batch_')) {
    return 88
  }

  return 10
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
        setStreamEvents((events) => mergeRequestEvents(events, data.stream_events))
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
        setStreamEvents((events) => mergeRequestEvents(events, [event]))
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
  const streamMonitor = buildStreamMonitor(streamEvents)
  const processingPercent = streamEvents.length
    ? streamMonitor.progressPercent
    : progressFromStage(request.stage_name)
  const isConnectingToModal =
    isAwaitingPrediction && !streamEvents.length && request.stage_name === 'modal_connecting'
  const processingLabel = streamEvents.length
    ? streamMonitor.activeLabel
    : formatModalLabel(request.stage_name ?? request.current_status)
  const processingCompletedSteps = streamEvents.length
    ? streamMonitor.completedSteps
    : new Set<string>()
  const solutionResults = buildSolutionResults(prediction)

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

      {streamEvents.length && !isAwaitingPrediction ? (
        <section className="panel request-stream-panel">
          <div className="request-stream-overview">
            <div>
              <p className="eyebrow">Modal inference stream</p>
              <h2>{streamMonitor.activeLabel}</h2>
              <span>
                {streamMonitor.modelName} model | {streamMonitor.totalRecords} record
                {streamMonitor.totalRecords === 1 ? '' : 's'} | batch {streamMonitor.batchLabel}
              </span>
            </div>
            <strong>{Math.round(streamMonitor.progressPercent)}%</strong>
          </div>
          <div
            aria-label="Modal inference progress"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={Math.round(streamMonitor.progressPercent)}
            className="request-stream-progress"
            role="progressbar"
          >
            <div style={{ width: `${streamMonitor.progressPercent}%` }} />
          </div>
          <div className="request-stream-steps">
            {streamMonitor.displaySteps.map((step, index) => {
              const isSkipped =
                streamMonitor.streamFinished &&
                !streamMonitor.completedSteps.has(step) &&
                !streamMonitor.seenSteps.has(step)

              return (
              <div
                className={
                  [
                    'request-stream-step',
                    streamMonitor.completedSteps.has(step) ? 'complete' : '',
                    streamMonitor.activeStep === step ? 'current' : '',
                    isSkipped ? 'skipped' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')
                }
                key={step}
              >
                <span>{index + 1}</span>
                <strong>{modalStepLabels[step]}</strong>
              </div>
              )
            })}
          </div>
          <div className="request-stream-track">
            {streamMonitor.events.slice(0, 5).map((event) => {
              const modalData = getModalData(event)
              const modalStep = getModalStep(event)
              const eventLabel = getModalEvent(event)
              const details = [
                modalData.status ? String(modalData.status) : '',
                modalData.embedding_rows ? `${modalData.embedding_rows} rows` : '',
                modalData.embedding_dim ? `${modalData.embedding_dim} dim` : '',
                modalData.tensor_shape ? `tensor ${String(modalData.tensor_shape)}` : '',
                modalData.prediction_rows ? `${modalData.prediction_rows} predictions` : '',
                modalData.batch_size ? `${modalData.batch_size} records` : '',
                event.payload.latency_ms ? `${event.payload.latency_ms} ms` : '',
              ].filter(Boolean)

              return (
              <div
                className="request-stream-event"
                key={`${event.eventType}-${event.receivedAt}`}
              >
                <span>{eventLabel}</span>
                <strong>
                  {formatModalLabel(
                    modalStep ||
                      (event.payload.stage_name ??
                        event.payload.current_status ??
                        event.payload.status ??
                        'event received'),
                  )}
                </strong>
                <small>
                  {details.length ? `${details.join(' | ')} | ` : ''}
                  {formatDateTime(event.receivedAt)}
                </small>
              </div>
              )
            })}
            {streamMonitor.events.length > 5 ? (
              <div className="request-stream-more">
                {streamMonitor.events.length - 5} older stream updates hidden
              </div>
            ) : null}
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

                {solutionResults.length > 1 ? (
                  <div className="solution-result-grid">
                    {solutionResults.map((solution) => {
                      const bestTerm = solution.terms[0]
                      return (
                        <section className="solution-result-card" key={solution.label}>
                          <div className="solution-result-header">
                            <div>
                              <span>{solution.role}</span>
                              <strong>{solution.label}</strong>
                            </div>
                            {solution.weight !== undefined ? (
                              <em>{formatScore(solution.weight)}</em>
                            ) : null}
                          </div>
                          {bestTerm ? (
                            <>
                              <div className="solution-top-term">
                                <strong>{bestTerm.term_id}</strong>
                                <span>{formatScore(bestTerm.score)}</span>
                              </div>
                              <p>{bestTerm.term_name ?? 'Unnamed ontology term'}</p>
                              <div className="score-track">
                                <div
                                  style={{
                                    width: `${Math.max(0, Math.min(100, bestTerm.score * 100))}%`,
                                  }}
                                />
                              </div>
                              <div className="solution-term-list">
                                {solution.terms.slice(1, 4).map((term) => (
                                  <span key={`${solution.label}-${term.term_id}`}>
                                    {term.term_id} {formatScore(term.score)}
                                  </span>
                                ))}
                              </div>
                            </>
                          ) : (
                            <p>No branch terms returned.</p>
                          )}
                        </section>
                      )
                    })}
                  </div>
                ) : null}

                {prediction.confidence_summary ? (
                  <p className="result-summary">{prediction.confidence_summary}</p>
                ) : null}
              </div>
            ) : request.current_status === 'completed' ? (
              <EmptyState message="No prediction result is available for this request." />
            ) : isAwaitingPrediction ? (
              <div className="prediction-processing">
                <div className="prediction-processing-header">
                  <div>
                    <span className="processing-dot" />
                    <strong>{request.current_status}</strong>
                  </div>
                  <em>{Math.round(processingPercent)}%</em>
                </div>
                <p>{processingLabel}</p>
                <div className="prediction-processing-stats">
                  <span>{request.model_version ?? streamMonitor.modelName} model</span>
                  <span>{requestInput?.sequence_length ?? '-'} amino acids</span>
                  <span>{streamEvents.length} stream updates</span>
                </div>
                <div
                  aria-label="Prediction is processing"
                  aria-valuemax={100}
                  aria-valuemin={0}
                  aria-valuenow={Math.round(processingPercent)}
                  className={
                    isConnectingToModal
                      ? 'processing-progress indeterminate'
                      : 'processing-progress'
                  }
                  role="progressbar"
                >
                  <div style={{ width: `${processingPercent}%` }} />
                </div>
                <div className="prediction-processing-steps">
                  {streamMonitor.displaySteps.map((step, index) => {
                    const isComplete = processingCompletedSteps.has(step)
                    const isCurrent =
                      !isComplete &&
                      streamEvents.length > 0 &&
                      streamMonitor.activeStep === step

                    return (
                      <div
                        className={[
                          'prediction-processing-step',
                          isComplete ? 'complete' : '',
                          isCurrent ? 'current' : '',
                        ]
                          .filter(Boolean)
                          .join(' ')}
                        key={step}
                      >
                        <span>{index + 1}</span>
                        <div>
                          <strong>{modalStepLabels[step]}</strong>
                          <small>{modalStepDescriptions[step]}</small>
                        </div>
                      </div>
                    )
                  })}
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
