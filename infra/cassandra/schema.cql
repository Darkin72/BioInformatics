CREATE KEYSPACE IF NOT EXISTS protein_rt
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

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
    confidence_summary text
);
