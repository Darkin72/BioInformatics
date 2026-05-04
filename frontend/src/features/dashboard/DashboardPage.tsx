import { useEffect, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { ErrorState } from '../../components/ErrorState'
import { LoadingState } from '../../components/LoadingState'
import { MetricCard } from '../../components/MetricCard'
import { StatusBadge } from '../../components/StatusBadge'
import { formatDateTime } from '../../shared/date'
import { formatLatency, formatPercent, formatScore } from '../../shared/format'
import type { DashboardLiveSnapshot, DashboardSummary } from '../../shared/types'
import { getDashboardSummary, openDashboardEvents } from './dashboardApi'

interface DashboardPageProps {
  isAdmin: boolean
  navigate: (path: string) => void
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
    }, 2000)

    return () => window.clearInterval(intervalId)
  }, [])

  useEffect(() => {
    if (!isAdmin) {
      setStreamState('offline')
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
  const statusCounts = {
    ...summary.status_counts,
    ...(scopedLiveSnapshot?.status_counts ?? {}),
  }
  const cassandraWriteTables =
    scopedLiveSnapshot?.cassandra.write_tables ?? summary.cassandra_write_tables
  const cassandraPatterns =
    scopedLiveSnapshot?.cassandra.active_query_patterns ??
    summary.cassandra_query_patterns
  const maxThroughput = Math.max(1, ...throughput.map((point) => point.metric_value))

  return (
    <section className="page-stack">
      <div className="section-header">
        <div>
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
          detail={`${summary.kafka_topics.length} topics observed`}
          label="Kafka stream"
          value={streamState === 'live' ? 'Live' : 'Waiting'}
        />
      </div>

      <section className="panel">
        <div className="section-header compact">
          <h2>Throughput</h2>
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
              />
              <span>{point.metric_value}</span>
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
            <span>Cassandra reads are modeled before tables</span>
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
