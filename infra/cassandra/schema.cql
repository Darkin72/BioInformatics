CREATE KEYSPACE IF NOT EXISTS protein_rt
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

CREATE TABLE IF NOT EXISTS protein_rt.request_status_by_id (
    request_id text PRIMARY KEY,
    request_date date,
    status_bucket text,
    protein_id text,
    username text,
    source text,
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

ALTER TABLE protein_rt.request_status_by_id
ADD IF NOT EXISTS request_date date;

ALTER TABLE protein_rt.request_status_by_id
ADD IF NOT EXISTS status_bucket text;

ALTER TABLE protein_rt.request_status_by_id
ADD IF NOT EXISTS username text;

ALTER TABLE protein_rt.request_status_by_id
ADD IF NOT EXISTS source text;

CREATE TABLE IF NOT EXISTS protein_rt.requests_by_day (
    request_date date,
    created_at timestamp,
    request_id text,
    protein_id text,
    username text,
    source text,
    updated_at timestamp,
    current_status text,
    error_code text,
    error_message text,
    stage_name text,
    retry_count int,
    model_version text,
    feature_version text,
    PRIMARY KEY (request_date, created_at, request_id)
) WITH CLUSTERING ORDER BY (created_at DESC, request_id ASC);

CREATE TABLE IF NOT EXISTS protein_rt.requests_by_status_window (
    status_bucket text,
    updated_at timestamp,
    request_id text,
    request_date date,
    protein_id text,
    username text,
    source text,
    current_status text,
    error_code text,
    error_message text,
    stage_name text,
    retry_count int,
    model_version text,
    feature_version text,
    PRIMARY KEY (status_bucket, updated_at, request_id)
) WITH CLUSTERING ORDER BY (updated_at DESC, request_id ASC);

CREATE TABLE IF NOT EXISTS protein_rt.requests_by_user_window (
    username_bucket text,
    created_at timestamp,
    request_id text,
    request_date date,
    protein_id text,
    username text,
    source text,
    updated_at timestamp,
    current_status text,
    error_code text,
    error_message text,
    stage_name text,
    retry_count int,
    model_version text,
    feature_version text,
    PRIMARY KEY (username_bucket, created_at, request_id)
) WITH CLUSTERING ORDER BY (created_at DESC, request_id ASC);

CREATE TABLE IF NOT EXISTS protein_rt.requests_by_protein_window (
    protein_bucket text,
    created_at timestamp,
    request_id text,
    request_date date,
    protein_id text,
    username text,
    source text,
    updated_at timestamp,
    current_status text,
    error_code text,
    error_message text,
    stage_name text,
    retry_count int,
    model_version text,
    feature_version text,
    PRIMARY KEY (protein_bucket, created_at, request_id)
) WITH CLUSTERING ORDER BY (created_at DESC, request_id ASC);

CREATE TABLE IF NOT EXISTS protein_rt.request_timeline_by_id (
    request_id text,
    event_ts timestamp,
    event_type text,
    stage_name text,
    status text,
    message text,
    latency_ms int,
    payload text,
    PRIMARY KEY (request_id, event_ts, event_type)
) WITH CLUSTERING ORDER BY (event_ts ASC, event_type ASC);

CREATE TABLE IF NOT EXISTS protein_rt.latest_prediction_by_protein (
    protein_id text PRIMARY KEY,
    request_id text,
    predicted_at timestamp,
    model_version text,
    top_terms list<text>,
    top_scores list<double>,
    confidence_summary text
);

CREATE TABLE IF NOT EXISTS protein_rt.prediction_history_by_protein (
    protein_id text,
    predicted_at timestamp,
    request_id text,
    model_version text,
    feature_version text,
    top_terms list<text>,
    top_scores list<double>,
    confidence_summary text,
    latency_ms int,
    PRIMARY KEY (protein_id, predicted_at, request_id)
) WITH CLUSTERING ORDER BY (predicted_at DESC, request_id ASC);

CREATE TABLE IF NOT EXISTS protein_rt.pipeline_metrics_by_window (
    metric_date date,
    metric_name text,
    window_start timestamp,
    window_end timestamp,
    metric_value double,
    tags map<text, text>,
    PRIMARY KEY ((metric_date, metric_name), window_start)
) WITH CLUSTERING ORDER BY (window_start DESC);

CREATE TABLE IF NOT EXISTS protein_rt.cassandra_serving_stats_by_day (
    stat_date date,
    stat_name text,
    updated_at timestamp,
    stat_value double,
    detail text,
    PRIMARY KEY (stat_date, stat_name)
);
