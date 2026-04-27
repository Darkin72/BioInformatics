import { useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { MetricCard } from '../../components/MetricCard'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import { formatLatency, formatPercent, formatScore } from '../../shared/format'
import type { DashboardSummary } from '../../shared/types'
import { getDashboardSummary } from './dashboardApi'

interface DashboardPageProps {
  navigate: (path: string) => void
}

export function DashboardPage({ navigate }: DashboardPageProps) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadSummary() {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getDashboardSummary()
      setSummary(data)
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load dashboard.',
      )
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let isActive = true

    getDashboardSummary()
      .then((data) => {
        if (isActive) {
          setSummary(data)
        }
      })
      .catch((loadError: unknown) => {
        if (isActive) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load dashboard.',
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
  }, [])

  if (isLoading) {
    return <LoadingState />
  }

  if (error) {
    return <ErrorState message={error} />
  }

  if (!summary) {
    return <EmptyState message="No dashboard data available." />
  }

  const maxThroughput = Math.max(
    ...summary.throughput.map((point) => point.metric_value),
  )

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
          <h2>Realtime overview</h2>
          <p>Updated {formatDateTime(summary.updated_at)}</p>
        </div>
        <button className="secondary-button" onClick={loadSummary} type="button">
          Refresh
        </button>
      </div>

      <div className="metric-grid">
        <MetricCard
          detail={`${summary.status_counts.processing} processing`}
          label="Requests today"
          value={summary.total_today.toLocaleString()}
        />
        <MetricCard
          detail={`p95 ${formatLatency(summary.p95_latency_ms)}`}
          label="Average latency"
          value={formatLatency(summary.avg_latency_ms)}
        />
        <MetricCard
          detail={`${summary.status_counts.failed} failed requests in mock store`}
          label="Error rate"
          value={formatPercent(summary.error_rate)}
        />
        <MetricCard
          detail={`${summary.status_counts.completed} completed`}
          label="Pipeline state"
          value="Healthy"
        />
      </div>

      <section className="panel">
        <div className="section-header compact">
          <h2>Throughput</h2>
          <span>events/minute</span>
        </div>
        <div className="bar-chart" aria-label="Throughput chart">
          {summary.throughput.map((point) => (
            <div className="bar-item" key={point.window_start}>
              <div
                className="bar-fill"
                style={{
                  height: `${Math.max(
                    12,
                    (point.metric_value / maxThroughput) * 100,
                  )}%`,
                }}
              />
              <span>{point.metric_value}</span>
            </div>
          ))}
        </div>
      </section>

      <div className="split-grid">
        <section className="panel">
          <div className="section-header compact">
            <h2>Recent predictions</h2>
            <button
              className="link-button"
              onClick={() => navigate('/proteins/P12345/latest')}
              type="button"
            >
              Open search
            </button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Protein</th>
                  <th>Top term</th>
                  <th>Score</th>
                  <th>Predicted</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_predictions.map((prediction) => (
                  <tr key={prediction.request_id}>
                    <td>
                      <button
                        className="table-link"
                        onClick={() =>
                          navigate(`/proteins/${prediction.protein_id}/latest`)
                        }
                        type="button"
                      >
                        {prediction.protein_id}
                      </button>
                    </td>
                    <td>{prediction.top_terms[0]?.term_id ?? '-'}</td>
                    <td>{formatScore(prediction.top_terms[0]?.score ?? 0)}</td>
                    <td>{formatDateTime(prediction.predicted_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="section-header compact">
            <h2>Failed requests</h2>
            <span>latest validation and inference errors</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Status</th>
                  <th>Stage</th>
                  <th>Error</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_failed_requests.map((request) => (
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
                    <td>
                      <StatusBadge status={request.current_status} />
                    </td>
                    <td>{request.stage_name ?? '-'}</td>
                    <td>{request.error_code ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  )
}
