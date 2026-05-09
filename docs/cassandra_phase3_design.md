# Cassandra phase 3 design

This note closes the remaining phase 3 design decisions for the local realtime
protein prediction stack.

## Partition cardinality

| Table | Partition key | Expected cardinality | Sizing note |
| --- | --- | --- | --- |
| `raw_protein_events` | `(ingest_date, shard_id)` | `days * 32` | Shard count caps hot partitions during replay bursts. |
| `request_status_by_id` | `request_id` | one row per request | Direct point lookup for status/result screens. |
| `requests_by_day` | `request_date` | one partition per day | Admin list query, bounded by day and page size. |
| `requests_by_status_window` | `status_bucket` | `days * status_count` | Bucket format is `YYYY-MM-DD#status`. |
| `requests_by_user_window` | `username_bucket` | `days * active_users` | Keeps user history reads single-partition. |
| `requests_by_protein_window` | `protein_bucket` | unique protein IDs | Protein-centric investigation. |
| `prediction_history_by_protein` | `protein_id` | unique protein IDs | Append-heavy but naturally bounded by prediction frequency. |
| `failed_requests_by_time` | `(failure_date, status_code)` | `days * error_codes` | Operator retry/debug view. |
| `pipeline_metrics_by_window` | `(metric_date, metric_name)` | `days * metric_names` | Time-window dashboard reads. |

## Partition size estimate

For local replay, a row is typically below 25 KB because the raw protein sequence
is the dominant field. With 32 shards, 100k records/day averages about 3125 rows
per raw-event partition. At 25 KB per row this is around 78 MB per hot partition,
which is acceptable for the dev/demo target. Higher sustained rates should raise
`shard_count` in `shard_for_request`.

`prediction_history_by_protein` is the main long-lived append table. The serving
API reads it with a limit, and duplicate `request_id` writes are guarded by
`prediction_by_request`.

## Consistency policy

| Flow | Write CL | Read CL | Reason |
| --- | --- | --- | --- |
| Raw ingest/replay | `LOCAL_QUORUM` in staging/prod, `ONE` locally | rarely read directly | Prefer durable ingest over low latency in real deployments. |
| Request status | `LOCAL_QUORUM` | `LOCAL_ONE` or `LOCAL_QUORUM` for operator actions | UI can tolerate slight staleness, retry decisions should prefer quorum. |
| Latest prediction | `LOCAL_QUORUM` | `LOCAL_QUORUM` | User-facing result should avoid stale reads. |
| Prediction history | `LOCAL_QUORUM` | `LOCAL_ONE` for list, `LOCAL_QUORUM` for audits | History lists are not control-plane critical. |
| Metrics | `ONE` | `ONE` | Dashboard metrics are approximate and continuously refreshed. |
| Failed requests | `LOCAL_QUORUM` | `LOCAL_QUORUM` | Retry/debug flow should be reliable. |

The local Docker Compose profile uses single-node Cassandra, so these policies
collapse to one replica during development.

## Compaction and TTL

| Table group | Compaction | TTL |
| --- | --- | --- |
| Raw events, failed requests | `TimeWindowCompactionStrategy` | 30 days |
| Metrics | `TimeWindowCompactionStrategy` | 90 days |
| Request status/materialized request lists | `SizeTieredCompactionStrategy` locally, `LeveledCompactionStrategy` if read-heavy | no TTL by default |
| Latest prediction | `LeveledCompactionStrategy` if read-heavy | no TTL |
| Prediction history | `TimeWindowCompactionStrategy` for high-volume replay campaigns | no TTL initially |

The current schema already sets TTL for raw events, failed requests, and metrics.

## Backup/restore

For local work, Cassandra data lives in the `cassandra_data` Docker volume and
can be recreated from `infra/cassandra/schema.cql`. For staging/prod, use daily
snapshots for serving tables plus incremental commitlog archiving for raw events
and failed requests. Restore order should be schema, request status, prediction
history/latest, then metrics.

## Retry and idempotency

Application retry is explicit:

- Serving API exposes `POST /api/inference-requests/{request_id}/retry`.
- RabbitMQ uses `command_exchange`, queue `retry_inference`, and routing key
  `request.retry` for stream-pipeline retries.
- `retry_worker` republishes retry payloads to the Kafka raw input topic.
- `prediction_by_request` acts as the idempotency guard for duplicate prediction
  writes; if a request already has a prediction row, duplicate writes are skipped.
