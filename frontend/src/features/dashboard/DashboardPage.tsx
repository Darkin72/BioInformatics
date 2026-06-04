import { useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { MetricCard } from '../../components/MetricCard'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import { formatLatency, formatPercent, formatScore } from '../../shared/format'
import type {
  DashboardLiveSnapshot,
  DashboardSummary,
  RequestStatus,
} from '../../shared/types'
import { getDashboardSummary, openDashboardEvents } from './dashboardApi'

interface DashboardPageProps {
  isAdmin: boolean
  navigate: (path: string) => void
}

const requestStatuses: RequestStatus[] = [
  'completed',
  'processing',
  'pending',
  'retrying',
  'failed',
  'cancelled',
]

const statusLabels: Record<RequestStatus, string> = {
  pending: 'Pending',
  processing: 'Processing',
  completed: 'Completed',
  failed: 'Failed',
  retrying: 'Retrying',
  cancelled: 'Cancelled',
}

const statusChartColors: Record<RequestStatus, string> = {
  completed: '#16a34a',
  processing: '#0ea5e9',
  pending: '#ca8a04',
  retrying: '#eab308',
  failed: '#dc2626',
  cancelled: '#94a3b8',
}

function percent(value: number, total: number) {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function formatMinuteLabel(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function buildDonutBackground(
  segments: Array<{ color: string; value: number }>,
  total: number,
) {
  if (total <= 0) {
    return '#e2e8f0'
  }

  let cursor = 0
  const stops = segments
    .filter((segment) => segment.value > 0)
    .map((segment) => {
      const start = cursor
      cursor += (segment.value / total) * 100
      return `${segment.color} ${start}% ${cursor}%`
    })

  return `conic-gradient(${stops.join(', ')})`
}

export function DashboardPage({ isAdmin, navigate }: DashboardPageProps) {
  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [liveSnapshot, setLiveSnapshot] = useState<DashboardLiveSnapshot | null>(
    null,
  )
  const [streamState, setStreamState] = useState<'connecting' | 'live' | 'offline'>(
    'connecting',
  )
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadSummary(showLoading = false) {
    if (showLoading) {
      setIsLoading(true)
    }
    try {
      const data = await getDashboardSummary()
      setSummary(data)
      setError(null)
    } catch (loadError) {
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Unable to load dashboard.',
      )
    } finally {
      if (showLoading) {
        setIsLoading(false)
      }
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

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadSummary(false)
    }, 10000)

    return () => window.clearInterval(intervalId)
  }, [])

  useEffect(() => {
    if (!isAdmin) {
      queueMicrotask(() => setStreamState('offline'))
      return undefined
    }

    const close = openDashboardEvents(
      (snapshot) => {
        setLiveSnapshot(snapshot)
        setStreamState('live')
      },
      () => {
        void loadSummary(false)
      },
      () => setStreamState('offline'),
    )

    return close
  }, [isAdmin])

  if (isLoading) {
    return <LoadingState />
  }

  if (error && !summary) {
    return <ErrorState message={error} />
  }

  if (!summary) {
    return <EmptyState message="No dashboard data available." />
  }

  const liveThroughputHasData =
    liveSnapshot?.throughput.some((point) => point.metric_value > 0) ?? false
  const summaryThroughputHasData = summary.throughput.some(
    (point) => point.metric_value > 0,
  )
  const scopedLiveSnapshot = isAdmin ? liveSnapshot : null
  const throughput =
    liveThroughputHasData || !summaryThroughputHasData
      ? scopedLiveSnapshot?.throughput ?? summary.throughput
      : summary.throughput
  const statusCounts = summary.status_counts
  const cassandraWriteTables =
    scopedLiveSnapshot?.cassandra.write_tables ?? summary.cassandra_write_tables
  const cassandraPatterns =
    scopedLiveSnapshot?.cassandra.active_query_patterns ??
    summary.cassandra_query_patterns
  const errorCounts = scopedLiveSnapshot?.error_codes ?? summary.error_counts
  const maxThroughput = Math.max(1, ...throughput.map((point) => point.metric_value))
  const totalRequests = requestStatuses.reduce(
    (total, status) => total + (statusCounts[status] ?? 0),
    0,
  )
  const statusSegments = requestStatuses.map((status) => ({
    status,
    label: statusLabels[status],
    color: statusChartColors[status],
    value: statusCounts[status] ?? 0,
  }))
  const statusDonutStyle: CSSProperties = {
    background: buildDonutBackground(statusSegments, totalRequests),
  }
  const avgLatency = scopedLiveSnapshot?.avg_latency_ms ?? summary.avg_latency_ms
  const p95Latency = scopedLiveSnapshot?.p95_latency_ms ?? summary.p95_latency_ms
  const maxLatency = Math.max(1, avgLatency, p95Latency)
  const cassandraEntries = Object.entries(cassandraWriteTables).sort(
    ([, left], [, right]) => right - left,
  )
  const cassandraWriteTotal = cassandraEntries.reduce(
    (total, [, writes]) => total + writes,
    0,
  )
  const maxCassandraWrites = Math.max(
    1,
    ...cassandraEntries.map(([, writes]) => writes),
  )
  const errorEntries = Object.entries(errorCounts).filter(([, count]) => count > 0)
  const maxErrors = Math.max(1, ...errorEntries.map(([, count]) => count))

  return (
    <section className="page-stack dashboard-page">
      <div className="section-header dashboard-hero">
        <div>
          <p className="eyebrow">CAFA-6 streaming inference</p>
          <h2>Realtime overview</h2>
          <p>
            Updated {formatDateTime(scopedLiveSnapshot?.updated_at ?? summary.updated_at)}
            {' | '}
            stream {streamState}
            {streamState === 'offline' ? ' | polling fallback active' : ''}
          </p>
        </div>
      </div>

      {error ? <ErrorState message={error} /> : null}

      <div className="dashboard-system-strip">
        <div>
          <span>Kafka topics</span>
          <strong>{summary.kafka_topics.length}</strong>
          <small>configured event topics</small>
        </div>
        <div>
          <span>Stream</span>
          <strong>{streamState}</strong>
          <small>{streamState === 'offline' ? 'polling fallback' : 'live updates'}</small>
        </div>
        <div>
          <span>Cassandra writes</span>
          <strong>{cassandraWriteTotal.toLocaleString()}</strong>
          <small>{cassandraEntries.length} serving tables</small>
        </div>
        <div>
          <span>P95 latency</span>
          <strong>{formatLatency(p95Latency)}</strong>
          <small>completed predictions</small>
        </div>
      </div>

      <div className="metric-grid">
        <MetricCard
          detail={`${statusCounts.processing} processing`}
          label="Requests today"
          value={summary.total_today.toLocaleString()}
        />
        <MetricCard
          detail={`p95 ${formatLatency(scopedLiveSnapshot?.p95_latency_ms ?? summary.p95_latency_ms)}`}
          label="Average latency"
          value={formatLatency(scopedLiveSnapshot?.avg_latency_ms ?? summary.avg_latency_ms)}
        />
        <MetricCard
          detail={`${statusCounts.failed} failed requests`}
          label="Error rate"
          value={formatPercent(summary.error_rate)}
        />
        <MetricCard
          detail={summary.kafka_topics.join(', ')}
          label="Kafka stream"
          value={streamState === 'live' ? 'Live' : 'Waiting'}
        />
      </div>

      <div className="dashboard-chart-grid">
        <section className="panel throughput-panel">
          <div className="section-header compact">
            <div>
              <h2>Throughput</h2>
              <p>Requests created per minute across the latest 8-minute window.</p>
            </div>
            <span>events/minute</span>
          </div>
          <div className="bar-chart" aria-label="Throughput chart">
            {throughput.map((point) => (
              <div className="bar-item" key={point.window_start}>
                <div
                  className="bar-fill"
                  style={{
                    height: `${Math.max(
                      12,
                      (point.metric_value / maxThroughput) * 100,
                    )}%`,
                  }}
                  title={`${point.metric_value} events at ${formatMinuteLabel(
                    point.window_start,
                  )}`}
                />
                <strong>{point.metric_value}</strong>
                <span>{formatMinuteLabel(point.window_start)}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="panel status-chart-panel">
          <div className="section-header compact">
            <div>
              <h2>Status distribution</h2>
              <p>{totalRequests.toLocaleString()} requests in the current scope.</p>
            </div>
          </div>
          <div className="status-donut-layout">
            <div
              aria-label="Request status distribution"
              className="status-donut"
              role="img"
              style={statusDonutStyle}
            >
              <div>
                <strong>{totalRequests.toLocaleString()}</strong>
                <span>Total</span>
              </div>
            </div>
            <div className="chart-legend">
              {statusSegments.map((segment) => (
                <div key={segment.status}>
                  <span
                    className="legend-dot"
                    style={{ background: segment.color }}
                  />
                  <strong>{segment.label}</strong>
                  <span>{segment.value.toLocaleString()}</span>
                  <span aria-hidden="true">·</span>
                  <span>{percent(segment.value, totalRequests)}%</span>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="split-grid">
        <section className="panel">
          <div className="section-header compact">
            <div>
              <h2>Latency window</h2>
              <p>Inference latency from completed predictions.</p>
            </div>
          </div>
          <div className="latency-chart">
            <div>
              <span>Average</span>
              <strong>{formatLatency(avgLatency)}</strong>
              <div className="score-track">
                <div style={{ width: `${percent(avgLatency, maxLatency)}%` }} />
              </div>
            </div>
            <div>
              <span>P95</span>
              <strong>{formatLatency(p95Latency)}</strong>
              <div className="score-track latency-p95">
                <div style={{ width: `${percent(p95Latency, maxLatency)}%` }} />
              </div>
            </div>
          </div>
        </section>

        {errorEntries.length > 0 ? (
          <section className="panel">
            <div className="section-header compact">
              <div>
                <h2>Error codes</h2>
                <p>Failed requests grouped by backend error code.</p>
              </div>
            </div>
            <div className="ranked-bar-list">
              {errorEntries.map(([code, count]) => (
                <div key={code}>
                  <div>
                    <span className="mono">{code}</span>
                    <strong>{count.toLocaleString()}</strong>
                  </div>
                  <div className="ranked-track">
                    <div style={{ width: `${percent(count, maxErrors)}%` }} />
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <section className="panel">
            <div className="section-header compact">
              <div>
                <h2>Error codes</h2>
                <p>No failed requests are currently reporting error codes.</p>
              </div>
            </div>
            <div className="zero-state-chart">
              <strong>{formatPercent(summary.error_rate)}</strong>
              <span>current error rate</span>
            </div>
          </section>
        )}
      </div>

      <section className="panel">
        <div className="section-header compact">
          <div>
            <h2>Cassandra write coverage</h2>
            <p>Expected denormalized writes by serving access pattern.</p>
          </div>
        </div>
        <div className="ranked-bar-list cassandra-bars">
          {cassandraEntries.map(([table, writes]) => (
            <div key={table}>
              <div>
                <span className="mono">{table}</span>
                <strong>{writes.toLocaleString()}</strong>
              </div>
              <div className="ranked-track">
                <div style={{ width: `${percent(writes, maxCassandraWrites)}%` }} />
              </div>
            </div>
          ))}
        </div>
      </section>

      <div className="split-grid">
        <section className="panel">
          <div className="section-header compact">
            <h2>Cassandra serving tables</h2>
            <span>denormalized writes by access pattern</span>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Table</th>
                  <th>Writes</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(cassandraWriteTables).map(([table, writes]) => (
                  <tr key={table}>
                    <td className="mono">{table}</td>
                    <td>{writes.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="section-header compact">
            <h2>Query patterns</h2>
            <span>Kafka topics are configured event channels</span>
          </div>
          <div className="tag-list">
            {cassandraPatterns.map((pattern) => (
              <span className="query-tag" key={pattern}>
                {pattern}
              </span>
            ))}
          </div>
          <div className="topic-row">
            {summary.kafka_topics.map((topic) => (
              <code key={topic}>{topic}</code>
            ))}
          </div>
        </section>
      </div>

      <div className="split-grid">
        <section className="panel">
          <div className="section-header compact">
            <h2>Recent requests</h2>
            {isAdmin ? (
              <button
                className="link-button"
                onClick={() => navigate('/admin/requests')}
                type="button"
              >
                Open requests
              </button>
            ) : null}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Request</th>
                  <th>Protein</th>
                  <th>Status</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {summary.recent_requests.map((request) => (
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
                    <td>{request.protein_id}</td>
                    <td>
                      <StatusBadge status={request.current_status} />
                    </td>
                    <td>{formatDateTime(request.updated_at ?? request.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel">
          <div className="section-header compact">
            <h2>Recent predictions</h2>
            <button
              className="link-button"
              onClick={() => navigate('/predictions')}
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
