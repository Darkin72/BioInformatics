CREATE TABLE IF NOT EXISTS dataset_catalog (
    dataset_id TEXT PRIMARY KEY,
    dataset_name TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    source_uri TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS model_registry (
    model_version TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    artifact_uri TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS replay_campaigns (
    replay_id TEXT PRIMARY KEY,
    dataset_id TEXT REFERENCES dataset_catalog(dataset_id),
    rate_per_second INTEGER NOT NULL DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'planned',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    config JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS operator_audit_log (
    audit_id BIGSERIAL PRIMARY KEY,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_operator_audit_log_created_at
    ON operator_audit_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_replay_campaigns_status
    ON replay_campaigns (status);
