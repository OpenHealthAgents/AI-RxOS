CREATE TABLE IF NOT EXISTS canonical.reconciliation_results (
    id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL CHECK (length(trim(source_type)) > 0),
    source_record_id TEXT NOT NULL CHECK (length(trim(source_record_id)) > 0),
    entity_type TEXT NOT NULL CHECK (length(trim(entity_type)) > 0),
    tenant_id UUID,
    canonical_entity_id UUID,
    status TEXT NOT NULL CHECK (status IN ('EXACT_MATCH', 'POSSIBLE_MATCH', 'AMBIGUOUS', 'UNRESOLVED', 'NEW_ENTITY')),
    match_method TEXT NOT NULL CHECK (length(trim(match_method)) > 0),
    match_reason TEXT NOT NULL CHECK (length(trim(match_reason)) > 0),
    candidate_ids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    source_namespace TEXT,
    source_identifier TEXT,
    source_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS reconciliation_results_scoped_unique
    ON canonical.reconciliation_results (source_type, source_record_id, entity_type, COALESCE(tenant_id, '00000000-0000-0000-0000-000000000000'::uuid));

CREATE INDEX IF NOT EXISTS reconciliation_results_status_idx
    ON canonical.reconciliation_results (status, entity_type, tenant_id, created_at DESC);
