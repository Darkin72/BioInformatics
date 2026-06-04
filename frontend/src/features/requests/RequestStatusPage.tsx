import { useCallback, useEffect, useRef, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type { PredictionTerm, RequestResult } from '../../shared/types'
import {
  getRequestProteinResult,
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
const proteinResultPageSize = 10
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
  calculating: 'Calculating',
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

function sortTermsByConfidence(terms: PredictionTerm[]) {
  return [...terms].sort((left, right) => right.score - left.score)
}

function GoTermTable({ terms }: { terms: PredictionTerm[] }) {
  const sortedTerms = sortTermsByConfidence(terms)

  return (
    <div className="go-term-table-wrap">
      <table className="go-term-table">
        <thead>
          <tr>
            <th>GO term</th>
            <th>Name</th>
            <th>Ontology</th>
            <th>Confidence</th>
            <th>Definition</th>
          </tr>
        </thead>
        <tbody>
          {sortedTerms.map((term, index) => (
            <tr key={`${term.term_id}-${term.ontology ?? ''}-${index}`}>
              <td>
                <strong className="protein-id-cell">{term.term_id}</strong>
              </td>
              <td>{term.term_name ?? 'Unnamed ontology term'}</td>
              <td>{formatOntology(term.ontology)}</td>
              <td>
                <strong>{formatScore(term.score)}</strong>
              </td>
              <td>{term.definition ?? '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function formatMetadataValue(value: unknown) {
  if (value === null || value === undefined || value === '') {
    return '-'
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)))
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No'
  }
  return String(value).replaceAll('_', ' ')
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

function isChunkScopedEvent(event: RequestStreamEvent) {
  const data = getModalData(event)
  return Number(data.total_chunks ?? 0) > 1 || data.chunk_index !== undefined
}

function isBatchProteinId(proteinId?: string | null) {
  return String(proteinId ?? '').toLowerCase().startsWith('batch:')
}

function buildStreamMonitor(
  events: RequestStreamEvent[],
  requestStatus?: string,
) {
  const chronological = [...events].sort(
    (left, right) => Date.parse(left.receivedAt) - Date.parse(right.receivedAt),
  )
  const progressEvents = chronological.filter((event) => getModalEvent(event) === 'progress')
  const batchEvents = chronological.filter((event) => getModalEvent(event) === 'batch')
  const seenSteps = new Set(
    progressEvents
      .map((event) => getModalStep(event))
      .filter(Boolean),
  )
  if (chronological.some((event) => getModalEvent(event) === 'start')) {
    seenSteps.add('normalize_input')
  }
  if (batchEvents.length) {
    seenSteps.add('normalize_input')
    seenSteps.add('batch_started')
  }
  const doneEvent = chronological.find(
    (event) => getModalEvent(event) === 'done' && !isChunkScopedEvent(event),
  )
  const hasCompletedPrediction = chronological.some(
    (event) =>
      event.eventType === 'prediction_result' &&
      String(event.payload.current_status ?? '').toLowerCase() === 'completed',
  )
  const streamFinished = Boolean(
    requestStatus === 'completed' || doneEvent || hasCompletedPrediction,
  )
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
  if (seenSteps.has('normalize_input')) {
    completedSteps.add('normalize_input')
  }
  if (batchEvents.length) {
    completedSteps.add('batch_started')
  }
  const latest = chronological.at(-1) ?? null
  const latestData = latest ? getModalData(latest) : {}
  const latestBatch = batchEvents.at(-1)
  const batchData = latestBatch ? getModalData(latestBatch) : {}
  const startEvent = chronological.find((event) => getModalEvent(event) === 'start')
  const startData = startEvent ? getModalData(startEvent) : {}
  const modelRecord = asRecord(batchData.model)
  const modelName = String(
    modelRecord.name ?? latestData.model ?? startData.model ?? 'ensemble',
  )
  const displaySteps = stepsForModel(modelName)
  if (streamFinished) {
    displaySteps.forEach((step) => completedSteps.add(step))
  } else {
    const highestSeenIndex = Math.max(
      -1,
      ...[...seenSteps].map((step) => displaySteps.indexOf(step)),
    )
    displaySteps.slice(0, highestSeenIndex).forEach((step) => completedSteps.add(step))
  }
  const chunkProgress = new Map<number, number>()
  let chunkTotal = 0
  chronological.forEach((event) => {
    const modalEvent = getModalEvent(event)
    const data = getModalData(event)
    const totalChunks = Number(data.total_chunks ?? 0)
    const chunkIndex = Number(data.chunk_index ?? -1)
    if (!Number.isFinite(totalChunks) || totalChunks <= 1 || chunkIndex < 0) {
      return
    }

    chunkTotal = Math.max(chunkTotal, totalChunks)
    const totalChunkBatches = Math.max(1, Number(data.total_batches ?? 1))
    const batchPosition = Math.min(
      totalChunkBatches,
      Number(data.batch_index ?? -1) + 1,
    )
    if (modalEvent !== 'batch' && modalEvent !== 'chunk_done') {
      return
    }

    const eventProgress = modalEvent === 'chunk_done'
      ? 1
      : batchPosition > 0
        ? batchPosition / totalChunkBatches
        : 0
    chunkProgress.set(
      chunkIndex,
      Math.max(chunkProgress.get(chunkIndex) ?? 0, eventProgress),
    )
  })
  const batchSharePercent = chunkTotal > 1
    ? [...chunkProgress.values()].reduce((sum, value) => sum + value, 0) / chunkTotal * 100
    : 0
  let maxBatchPosition = 0
  let maxTotalBatches = 1
  batchEvents.forEach((event) => {
    if (isChunkScopedEvent(event)) {
      return
    }
    const data = getModalData(event)
    const total = Math.max(1, Number(data.total_batches ?? 1))
    const position = Math.min(total, Number(data.batch_index ?? -1) + 1)
    if (position > maxBatchPosition) {
      maxBatchPosition = position
      maxTotalBatches = total
    }
  })
  const singleStreamBatchPercent = maxBatchPosition > 0
    ? (maxBatchPosition / maxTotalBatches) * 100
    : 0
  const batchProgressPercent = batchSharePercent || singleStreamBatchPercent
  const normalizedPercent = seenSteps.has('normalize_input') ? 25 : 0
  const queuedPercent = seenSteps.has('batch_started') ? 25 : 0
  const progressPercent = streamFinished
    ? 100
    : Math.min(99, normalizedPercent + queuedPercent + batchProgressPercent * 0.5)
  const totalRecords = Number(
    latestData.total_records ?? batchData.total_records ?? startData.total_input_records ?? 1,
  )
  const totalBatches = Number(
    maxBatchPosition > 0
      ? maxTotalBatches
      : latestData.total_batches ?? batchData.total_batches ?? 1,
  )
  const batchIndex = Number(
    maxBatchPosition > 0
      ? maxBatchPosition - 1
      : latestData.batch_index ?? batchData.batch_index ?? -1,
  )
  const activeStep = streamFinished
    ? ''
    : progressPercent >= 50
      ? 'calculating'
      : progressPercent >= 25
        ? 'batch_started'
        : progressPercent > 0
          ? 'normalize_input'
          : ''
  const simplifiedSteps = ['normalize_input', 'batch_started', 'calculating']
  const simplifiedCompletedSteps = new Set<string>()
  if (progressPercent >= 25) {
    simplifiedCompletedSteps.add('normalize_input')
  }
  if (progressPercent >= 50) {
    simplifiedCompletedSteps.add('batch_started')
  }
  if (streamFinished) {
    simplifiedSteps.forEach((step) => simplifiedCompletedSteps.add(step))
  }
  const simplifiedSeenSteps = new Set<string>()
  if (progressPercent > 0 || streamFinished) {
    simplifiedSeenSteps.add('normalize_input')
  }
  if (progressPercent >= 25 || streamFinished) {
    simplifiedSeenSteps.add('batch_started')
  }
  if (progressPercent >= 50 || streamFinished) {
    simplifiedSeenSteps.add('calculating')
  }
  const latestStepLabel = latest
    ? formatModalLabel(
        getModalStep(latest) || latest.payload.stage_name || getModalEvent(latest),
      )
    : 'Waiting for stream'

  return {
    activeLabel: latest
      ? streamFinished
        ? formatModalLabel('prediction_written')
        : latestStepLabel
      : 'Waiting for stream',
    activeStep,
    batchLabel: `${Math.max(0, Math.min(batchIndex + 1, totalBatches))} / ${totalBatches}`,
    completedSteps: simplifiedCompletedSteps,
    displaySteps: simplifiedSteps,
    chunkProgressLabel: chunkTotal > 1
      ? `${Math.round(Math.min(100, batchSharePercent))}% across ${chunkTotal} chunks`
      : '',
    events: chronological.slice(-24).reverse(),
    modelName,
    progressPercent,
    seenSteps: simplifiedSeenSteps,
    streamFinished,
    totalRecords: Number.isFinite(totalRecords) ? totalRecords : 1,
  }
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
  requestId,
  navigate,
}: RequestStatusPageProps) {
  const [streamEvents, setStreamEvents] = useState<RequestStreamEvent[]>([])
  const [isStreamLogOpen, setIsStreamLogOpen] = useState(false)
  const [proteinResultPage, setProteinResultPage] = useState(1)
  const progressPeakRef = useRef({ requestId: '', value: 0 })
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

  const loadRequestResult = useCallback((options: { suppressError?: boolean } = {}) => {
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
        if (options.suppressError) {
          return
        }
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
    setIsStreamLogOpen(false)
    setProteinResultPage(1)
    progressPeakRef.current = { requestId, value: 0 }

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
      void loadRequestResult({ suppressError: true })
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [loadRequestResult, request])

  useEffect(() => {
    const close = openRequestEvents(
      requestId,
      (event) => {
        setStreamEvents((events) => mergeRequestEvents(events, [event]))
        const status = String(event.payload.current_status ?? '').toLowerCase()
        if (
          event.eventType === 'prediction_result' ||
          status === 'completed' ||
          status === 'failed'
        ) {
          void loadRequestResult({ suppressError: true })
        }
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
  const proteinResults = result?.protein_results ?? []
  const requestInput = result?.input ?? null
  const inputRecords = requestInput?.records ?? []
  const proteinInputRecords = inputRecords.filter(
    (record) => !isBatchProteinId(record.protein_id),
  )
  const displayedProteinResults = proteinResults.filter(
    (item) => !isBatchProteinId(item.protein_id),
  )
  const displayedProteinCount = proteinInputRecords.length || displayedProteinResults.length
  const hasProteinTable = displayedProteinCount > 1
  const predictedAt = prediction?.predicted_at
    ? formatDateTime(prediction.predicted_at)
    : null
  const isAwaitingPrediction = pollingStatuses.has(request.current_status)
  const streamMonitor = buildStreamMonitor(streamEvents, request.current_status)
  const rawProcessingPercent = streamEvents.length
    ? streamMonitor.progressPercent
    : 0
  const rawStreamProgressPercent = request.current_status === 'completed'
    ? 100
    : rawProcessingPercent
  if (progressPeakRef.current.requestId !== request.request_id) {
    progressPeakRef.current = { requestId: request.request_id, value: 0 }
  }
  progressPeakRef.current.value = Math.max(
    progressPeakRef.current.value,
    rawStreamProgressPercent,
  )
  const streamProgressPercent = progressPeakRef.current.value
  const processingPercent = streamProgressPercent
  const isConnectingToModal =
    isAwaitingPrediction && !streamEvents.length && request.stage_name === 'modal_connecting'
  const processingLabel = streamEvents.length
    ? streamMonitor.activeLabel
    : formatModalLabel(request.stage_name ?? request.current_status)
  const processingCompletedSteps = streamEvents.length
    ? streamMonitor.completedSteps
    : request.current_status === 'completed'
      ? new Set(streamMonitor.displaySteps)
    : new Set<string>()
  const shouldShowStreamProgress =
    streamEvents.length > 0 || isAwaitingPrediction || request.current_status === 'completed'
  const streamRecordCount =
    displayedProteinCount || streamMonitor.totalRecords
  const streamModelName =
    request.model_version?.replace(/^cafa6-modal-/, '') || streamMonitor.modelName
  const inputMetadata = asRecord(requestInput?.metadata)
  const requestProteinIds = proteinInputRecords.map((record) => record.protein_id)
  const inputProteinCount = displayedProteinCount || Number(
    inputMetadata.fasta_record_count ?? inputMetadata.protein_count ?? 0,
  )
  const proteinRows = (proteinInputRecords.length ? proteinInputRecords : displayedProteinResults.map((item) => ({
    protein_id: item.protein_id,
    sequence_length: null,
    description: null,
  }))).map((record) => ({
    ...record,
    prediction: displayedProteinResults.find(
      (item) => item.protein_id.toLowerCase() === record.protein_id.toLowerCase(),
    ),
  }))
  const predictionRows = proteinRows.filter((row) => Boolean(row.prediction))
  const proteinResultPageCount = Math.max(
    1,
    Math.ceil(proteinRows.length / proteinResultPageSize),
  )
  const activeProteinResultPage = Math.min(
    proteinResultPage,
    proteinResultPageCount,
  )
  const proteinResultStartIndex = (activeProteinResultPage - 1) * proteinResultPageSize
  const paginatedProteinRows = proteinRows.slice(
    proteinResultStartIndex,
    proteinResultStartIndex + proteinResultPageSize,
  )
  const visibleStreamEvents = isStreamLogOpen
    ? streamMonitor.events
    : []

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

      {shouldShowStreamProgress ? (
        <section className="panel request-stream-panel">
          <div className="request-stream-overview">
            <div>
              <p className="eyebrow">Modal inference stream</p>
              <h2>{processingLabel}</h2>
              <span>
                {streamModelName} model | {streamRecordCount} record
                {streamRecordCount === 1 ? '' : 's'}
              </span>
            </div>
            <strong>{Math.round(streamProgressPercent)}%</strong>
          </div>
          <div
            aria-label="Modal inference progress"
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={Math.round(streamProgressPercent)}
            className="request-stream-progress"
            role="progressbar"
          >
            <div style={{ width: `${streamProgressPercent}%` }} />
          </div>
          <div className="request-stream-steps">
            {streamMonitor.displaySteps.map((step, index) => {
              const isSkipped =
                streamMonitor.streamFinished &&
                !processingCompletedSteps.has(step) &&
                !streamMonitor.seenSteps.has(step)

              return (
              <div
                className={
                  [
                    'request-stream-step',
                    processingCompletedSteps.has(step) ? 'complete' : '',
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
          <div className="request-stream-log-header">
            <span>{streamMonitor.events.length} stream updates</span>
            <button
              className="secondary-button compact-button"
              onClick={() => setIsStreamLogOpen((current) => !current)}
              type="button"
            >
              {isStreamLogOpen ? 'Collapse log' : 'Show log'}
            </button>
          </div>
          {isStreamLogOpen ? (
            <div className="request-stream-track open">
              {visibleStreamEvents.map((event) => {
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
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header compact request-input-header">
          <h2>Request input</h2>
          <span>
            {hasProteinTable
              ? `${inputProteinCount} proteins`
              : requestInput?.sequence_length
                ? `${requestInput.sequence_length} amino acids`
                : 'Input summary'}
          </span>
        </div>

        {requestInput ? (
          <div className="input-result">
            <div className="request-input-overview">
              <div className="request-input-card primary">
                <span>{hasProteinTable ? 'Protein foreign keys' : 'Protein ID'}</span>
                <strong>
                  {hasProteinTable
                    ? `${requestProteinIds.length} protein IDs`
                    : requestInput.protein_id}
                </strong>
                <small>
                  {hasProteinTable
                    ? requestProteinIds.slice(0, 4).join(', ')
                    : `${requestInput.sequence_length ?? '-'} amino acids`}
                </small>
                {hasProteinTable && requestProteinIds.length > 4 ? (
                  <small>+{requestProteinIds.length - 4} more linked proteins</small>
                ) : null}
              </div>
              <div className="request-input-card">
                <span>Source</span>
                <strong>{requestInput.source ?? request.source ?? '-'}</strong>
                <small>{request.username ?? 'current user'}</small>
              </div>
              <div className="request-input-card">
                <span>Model</span>
                <strong>{formatMetadataValue(inputMetadata.model ?? request.model_version)}</strong>
                <small>
                  Top K {formatMetadataValue(inputMetadata.top_k)} · Threshold{' '}
                  {formatMetadataValue(inputMetadata.threshold)}
                </small>
              </div>
              <div className="request-input-card">
                <span>FASTA</span>
                <strong>{formatMetadataValue(inputProteinCount || inputMetadata.fasta_record_count)}</strong>
                <small title={String(inputMetadata.fasta_description ?? '')}>
                  {inputMetadata.fasta_description
                    ? formatMetadataValue(inputMetadata.fasta_description)
                    : 'Protein sequence is available in each protein detail.'}
                </small>
              </div>
            </div>
          </div>
        ) : (
          <EmptyState message="Input was not stored for this request." />
        )}
      </section>

      <section className="panel">
        <div className="section-header compact">
          <h2>Prediction result</h2>
          <div className="section-header-actions">
            {predictedAt ? <span>{predictedAt}</span> : null}
          </div>
        </div>

        {(
          <>
            {hasProteinTable && proteinRows.length ? (
              <>
                <div className="prediction-result-summary">
                  <div>
                    <span>Records shown</span>
                    <strong>{proteinRows.length}</strong>
                  </div>
                  <div>
                    <span>With GO terms</span>
                    <strong>{predictionRows.length}</strong>
                  </div>
                  <div>
                    <span>Coverage</span>
                    <strong>
                      {proteinRows.length
                        ? `${Math.round((predictionRows.length / proteinRows.length) * 100)}%`
                        : '0%'}
                    </strong>
                  </div>
                </div>
                <div className="protein-result-table-wrap">
                  <table className="protein-result-table">
                    <thead>
                      <tr>
                        <th>Protein ID</th>
                        <th>Terms</th>
                        <th className="protein-result-action-heading">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {paginatedProteinRows.map((row) => (
                        <tr key={`prediction-${row.protein_id}`}>
                          <td>
                            <strong className="protein-id-cell">{row.protein_id}</strong>
                          </td>
                          <td>{row.prediction?.top_terms.length ?? 0}</td>
                          <td className="protein-result-action-cell">
                            {row.prediction ? (
                              <button
                                className="secondary-button compact-button protein-open-button"
                                onClick={() =>
                                  navigate(
                                    `/requests/${request.request_id}/proteins/${row.protein_id}`,
                                  )
                                }
                                type="button"
                              >
                                Open
                              </button>
                            ) : (
                              <span className="protein-result-empty">No terms</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="pagination-row protein-result-pagination">
                  <button
                    className="secondary-button compact-button"
                    disabled={activeProteinResultPage <= 1}
                    onClick={() =>
                      setProteinResultPage((current) => Math.max(1, current - 1))
                    }
                    type="button"
                  >
                    Previous
                  </button>
                  <span>
                    Page {activeProteinResultPage} of {proteinResultPageCount} | Showing{' '}
                    {proteinRows.length ? proteinResultStartIndex + 1 : 0}-
                    {Math.min(proteinResultStartIndex + proteinResultPageSize, proteinRows.length)} of{' '}
                    {proteinRows.length} records
                  </span>
                  <button
                    className="secondary-button compact-button"
                    disabled={activeProteinResultPage >= proteinResultPageCount}
                    onClick={() =>
                      setProteinResultPage((current) =>
                        Math.min(proteinResultPageCount, current + 1),
                      )
                    }
                    type="button"
                  >
                    Next
                  </button>
                </div>
              </>
            ) : hasProteinTable ? (
              <div className="prediction-empty-panel">
                <div>
                  <span>Predicted proteins</span>
                  <strong>{predictionRows.length}</strong>
                </div>
                <div>
                  <span>Total proteins</span>
                  <strong>{proteinRows.length}</strong>
                </div>
                <p>
                  {isAwaitingPrediction
                    ? 'Predictions are still being written. This table will appear when per-protein results arrive.'
                    : 'No per-protein predictions were stored for this request. Older completed requests may need to be submitted again after the per-protein persistence fix.'}
                </p>
              </div>
            ) : prediction?.top_terms.length ? (
              <div className="prediction-result">
                <dl className="prediction-summary">
                  <div>
                    <dt>Protein</dt>
                    <dd>{prediction.protein_id}</dd>
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

                <GoTermTable terms={prediction.top_terms} />

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

          </>
        )}
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

export function RequestProteinDetailPage({
  proteinId,
  requestId,
  navigate,
}: {
  proteinId: string
  requestId: string
  navigate: (path: string) => void
}) {
  const [prediction, setPrediction] = useState<PredictionTerm[] | null>(null)
  const [header, setHeader] = useState<{
    modelVersion: string
    predictedAt: string
    summary?: string | null
  } | null>(null)
  const [inputRecord, setInputRecord] = useState<{
    sequence?: string | null
    sequence_length?: number | null
    description?: string | null
  } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isActive = true
    setPrediction(null)
    setHeader(null)
    setInputRecord(null)
    setError(null)

    Promise.all([
      getRequestProteinResult(requestId, proteinId),
      getRequestResult(requestId).catch(() => null),
    ])
      .then(([result, requestResult]) => {
        if (!isActive) {
          return
        }
        const matchingRecord = requestResult?.input?.records?.find(
          (record) => record.protein_id.toLowerCase() === proteinId.toLowerCase(),
        )
        const directInputRecord = requestResult?.input && !requestResult.input.records
          ? {
              sequence: requestResult.input.sequence,
              sequence_length: requestResult.input.sequence_length,
              description: null,
            }
          : null
        setPrediction(result.top_terms)
        setHeader({
          modelVersion: result.model_version,
          predictedAt: result.predicted_at,
          summary: result.confidence_summary,
        })
        setInputRecord(matchingRecord ?? directInputRecord ?? null)
      })
      .catch((loadError: unknown) => {
        if (!isActive) {
          return
        }
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load protein result.',
        )
      })

    return () => {
      isActive = false
    }
  }, [proteinId, requestId])

  if (error) {
    return <ErrorState message={error} />
  }

  if (!prediction || !header) {
    return <LoadingState />
  }

  return (
    <section className="page-stack">
      <div className="section-header protein-detail-header">
        <button
          aria-label="Back to request"
          className="icon-button protein-back-button"
          onClick={() => navigate(`/requests/${requestId}`)}
          title="Back to request"
          type="button"
        >
          <svg aria-hidden="true" className="ui-icon" viewBox="0 0 24 24">
            <path d="M19 12H5" />
            <path d="M12 19l-7-7 7-7" />
          </svg>
        </button>
        <div>
          <h2>{proteinId}</h2>
          <p className="mono">{requestId}</p>
        </div>
      </div>

      <section className="panel">
        <dl className="prediction-summary">
          <div>
            <dt>Protein ID</dt>
            <dd>{proteinId}</dd>
          </div>
          <div>
            <dt>Length</dt>
            <dd>{inputRecord?.sequence_length ?? '-'}</dd>
          </div>
          <div>
            <dt>Model</dt>
            <dd>{header.modelVersion}</dd>
          </div>
          <div>
            <dt>Predicted</dt>
            <dd>{formatDateTime(header.predictedAt)}</dd>
          </div>
          <div>
            <dt>Terms returned</dt>
            <dd>{prediction.length}</dd>
          </div>
        </dl>
        {header.summary ? <p className="result-summary">{header.summary}</p> : null}
        <div className="sequence-section">
          <div className="sequence-section-header">
            <div>
              <span>Input sequence</span>
              <strong>{inputRecord?.sequence_length ?? inputRecord?.sequence?.length ?? '-'} residues</strong>
            </div>
            {inputRecord?.description ? <small>{inputRecord.description}</small> : null}
          </div>
          {inputRecord?.sequence ? (
            <pre className="sequence-view">{inputRecord.sequence}</pre>
          ) : (
            <p className="sequence-empty">
              Sequence text was not stored for this older request; new requests store it in the request timeline.
            </p>
          )}
        </div>
      </section>

      <section className="panel">
        <GoTermTable terms={prediction} />
      </section>
    </section>
  )
}
