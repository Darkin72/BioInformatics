import { useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import type { InferenceRequest } from '../../shared/types'
import { getRequestStatus } from './requestsApi'

interface RequestStatusPageProps {
  requestId: string
  navigate: (path: string) => void
}

const pollingStatuses = new Set(['pending', 'processing', 'retrying'])

export function RequestStatusPage({
  requestId,
  navigate,
}: RequestStatusPageProps) {
  const [remoteState, setRemoteState] = useState<{
    requestId: string
    request: InferenceRequest | null
    error: string | null
  }>({
    requestId: '',
    request: null,
    error: null,
  })

  async function loadRequest() {
    try {
      const data = await getRequestStatus(requestId)
      setRemoteState({
        requestId,
        request: { ...data },
        error: null,
      })
    } catch (loadError) {
      setRemoteState({
        requestId,
        request: null,
        error:
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load request status.',
      })
    }
  }

  useEffect(() => {
    let isActive = true

    getRequestStatus(requestId)
      .then((data) => {
        if (isActive) {
          setRemoteState({
            requestId,
            request: { ...data },
            error: null,
          })
        }
      })
      .catch((loadError: unknown) => {
        if (isActive) {
          setRemoteState({
            requestId,
            request: null,
            error:
              loadError instanceof Error
                ? loadError.message
                : 'Unable to load request status.',
          })
        }
      })

    return () => {
      isActive = false
    }
  }, [requestId])

  const request =
    remoteState.requestId === requestId ? remoteState.request : null
  const error = remoteState.requestId === requestId ? remoteState.error : null
  const isLoading = remoteState.requestId !== requestId

  useEffect(() => {
    if (!request || !pollingStatuses.has(request.current_status)) {
      return
    }

    const intervalId = window.setInterval(() => {
      getRequestStatus(requestId)
        .then((data) => {
          setRemoteState({
            requestId,
            request: { ...data },
            error: null,
          })
        })
        .catch((loadError: unknown) => {
          setRemoteState({
            requestId,
            request: null,
            error:
              loadError instanceof Error
                ? loadError.message
                : 'Unable to load request status.',
          })
        })
    }, 5000)

    return () => window.clearInterval(intervalId)
  }, [request, requestId])

  if (isLoading) {
    return <LoadingState />
  }

  if (error) {
    return <ErrorState message={error} />
  }

  if (!request) {
    return <EmptyState message="Request not found." />
  }

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>Request status</h2>
          <p className="mono">{request.request_id}</p>
        </div>
        <StatusBadge status={request.current_status} />
      </div>

      <section className="panel">
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
          <button className="secondary-button" onClick={loadRequest} type="button">
            Refresh
          </button>
          <button
            className="secondary-button"
            onClick={() => navigate(`/proteins/${request.protein_id}/latest`)}
            type="button"
          >
            Open latest prediction
          </button>
        </div>
      </section>
    </section>
  )
}
