-- ==============================================================================
-- Migration: 039_async_ingestion_orchestration.sql
-- Description: Asynchronous Ingestion Orchestration, Scheduling, Watermarking,
-- Dead-Letter Queue (DLQ), and Observability Schema.
-- Guarantees:
-- 1. Scheduled ingestion & stateful execution history
-- 2. Incremental updates & high-watermark tracking
-- 3. Exponential backoff retry policies
-- 4. Zero silent failures: Dead-letter isolation with complete payload & diagnostic preservation
-- 5. Content-hash deduplication
-- 6. Observability metrics & health telemetry
-- 7. Data-quality validation gates
-- ==============================================================================

-- 1. Ingestion Pipelines Configuration & Live State
CREATE TABLE IF NOT EXISTS ingestion_pipelines (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    source_name VARCHAR(128) NOT NULL,
    schedule_interval_seconds INTEGER,
    schedule_cron VARCHAR(64),
    is_schedule_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    next_run_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'IDLE' CHECK (
        status IN ('IDLE', 'RUNNING', 'PAUSED', 'ERROR')
    ),
    last_watermark_timestamp TIMESTAMPTZ,
    last_watermark_id VARCHAR(128),
    quality_gate_strict BOOLEAN NOT NULL DEFAULT TRUE,
    max_retries INTEGER NOT NULL DEFAULT 3,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipelines_status ON ingestion_pipelines (status);
CREATE INDEX IF NOT EXISTS idx_pipelines_next_run ON ingestion_pipelines (next_run_at);

-- 2. Ingestion Run Execution History & Telemetry
CREATE TABLE IF NOT EXISTS ingestion_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id VARCHAR(64) NOT NULL REFERENCES ingestion_pipelines(id) ON DELETE CASCADE,
    triggered_by VARCHAR(64) NOT NULL DEFAULT 'MANUAL',
    status VARCHAR(32) NOT NULL CHECK (
        status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL_SUCCESS', 'FAILED')
    ),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    items_fetched INTEGER NOT NULL DEFAULT 0,
    items_processed INTEGER NOT NULL DEFAULT 0,
    items_succeeded INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,
    items_retried INTEGER NOT NULL DEFAULT 0,
    items_deduplicated INTEGER NOT NULL DEFAULT 0,
    items_dead_lettered INTEGER NOT NULL DEFAULT 0,
    duration_seconds NUMERIC(10, 4) NOT NULL DEFAULT 0,
    error_message TEXT,
    telemetry_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_pipeline_started ON ingestion_runs (pipeline_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status ON ingestion_runs (status);

-- 3. Ingestion Dead-Letter Queue (DLQ)
CREATE TABLE IF NOT EXISTS ingestion_dead_letter_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id VARCHAR(64) NOT NULL REFERENCES ingestion_pipelines(id) ON DELETE CASCADE,
    item_id VARCHAR(255) NOT NULL,
    source VARCHAR(128) NOT NULL,
    payload JSONB NOT NULL,
    failure_reason TEXT NOT NULL,
    failure_category VARCHAR(128) NOT NULL,
    stack_trace TEXT,
    retry_attempts INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'REPLAYED', 'RESOLVED', 'DISCARDED')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_note TEXT
);

CREATE INDEX IF NOT EXISTS idx_dlq_status ON ingestion_dead_letter_queue (status);
CREATE INDEX IF NOT EXISTS idx_dlq_pipeline_status ON ingestion_dead_letter_queue (pipeline_id, status);
CREATE INDEX IF NOT EXISTS idx_dlq_item ON ingestion_dead_letter_queue (source, item_id);

-- 4. Ingestion Deduplication Hashes
CREATE TABLE IF NOT EXISTS ingestion_deduplication_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id VARCHAR(64) NOT NULL,
    item_id VARCHAR(255) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pipeline_item UNIQUE (pipeline_id, item_id),
    CONSTRAINT uq_pipeline_hash UNIQUE (pipeline_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_dedup_hash ON ingestion_deduplication_records (pipeline_id, content_hash);
