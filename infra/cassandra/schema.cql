CREATE KEYSPACE IF NOT EXISTS protein_rt
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS protein_rt.raw_protein_events (
    ingest_date date,
    shard_id int,
    event_ts timestamp,
    request_id text,
    protein_id text,
    source_type text,
    sequence_raw text,
    source_payload text,
    checksum text,
    producer_id text,
    PRIMARY KEY ((ingest_date, shard_id), event_ts, request_id)
) WITH CLUSTERING ORDER BY (event_ts DESC)
  AND default_time_to_live = 2592000;

CREATE TABLE IF NOT EXISTS protein_rt.request_status_by_id (
    request_id text PRIMARY KEY,
    protein_id text,
    created_at timestamp,
    updated_at timestamp,
    current_status text,
    error_code text,
    error_message text,
    stage_name text,
    retry_count int,
    model_version text,
    feature_version text
);

CREATE TABLE IF NOT EXISTS protein_rt.latest_prediction_by_protein (
    protein_id text PRIMARY KEY,
    request_id text,
    predicted_at timestamp,
    model_version text,
    top_terms list<text>,
    top_scores list<double>,
    prediction_rows list<text>,
    confidence_summary text,
    explanation_ref text,
    embedding_ref text
);

ALTER TABLE protein_rt.latest_prediction_by_protein
ADD IF NOT EXISTS prediction_rows list<text>;

CREATE TABLE IF NOT EXISTS protein_rt.prediction_history_by_protein (
    protein_id text,
    predicted_at timestamp,
    request_id text,
    model_version text,
    feature_version text,
    predicted_terms list<text>,
    score_map map<text, double>,
    prediction_rows list<text>,
    threshold_used double,
    latency_ms int,
    PRIMARY KEY (protein_id, predicted_at, request_id)
) WITH CLUSTERING ORDER BY (predicted_at DESC, request_id ASC);

CREATE TABLE IF NOT EXISTS protein_rt.prediction_by_request (
    request_id text PRIMARY KEY,
    protein_id text,
    predicted_at timestamp,
    model_version text,
    feature_version text,
    predicted_terms list<text>,
    score_map map<text, double>,
    prediction_rows list<text>,
    threshold_used double,
    latency_ms int
);

CREATE TABLE IF NOT EXISTS protein_rt.failed_requests_by_time (
    failure_date date,
    status_code text,
    failed_at timestamp,
    request_id text,
    protein_id text,
    stage_name text,
    reason text,
    retryable boolean,
    PRIMARY KEY ((failure_date, status_code), failed_at, request_id)
) WITH CLUSTERING ORDER BY (failed_at DESC, request_id ASC)
  AND default_time_to_live = 2592000;

CREATE TABLE IF NOT EXISTS protein_rt.pipeline_metrics_by_window (
    metric_date date,
    metric_name text,
    window_start timestamp,
    window_end timestamp,
    metric_value double,
    tags map<text, text>,
    PRIMARY KEY ((metric_date, metric_name), window_start)
) WITH CLUSTERING ORDER BY (window_start DESC)
  AND default_time_to_live = 7776000;

CREATE TABLE IF NOT EXISTS protein_rt.feature_snapshot_by_request (
    request_id text PRIMARY KEY,
    protein_id text,
    feature_version text,
    generated_at timestamp,
    feature_hash text,
    feature_payload_ref text,
    embedding_vector_ref text
);
