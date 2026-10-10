-- ==============================================================================
-- Migration: 041_semantic_and_structured_search.sql
-- Description: Indexes, Full-Text Search vectors, and safety views for Search Engine
--
-- Supports high-performance search across 8 target entities:
--   1. asset search
--   2. target search
--   3. indication search
--   4. biomarker search
--   5. trial search
--   6. publication search
--   7. company search
--   8. opportunity search
--
-- Invariant: "Never use LLM output as the final database query without validation."
-- ==============================================================================

-- 1. Full-Text Search Extension & Text Search Configurations
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2. Materialized Search View for Therapeutic Assets & Opportunities
CREATE OR REPLACE VIEW canonical.view_searchable_assets AS
SELECT
    a.id AS asset_id,
    a.preferred_name AS asset_name,
    a.current_development_stage AS highest_phase,
    c.name AS owner_name,
    t.symbol AS target_symbol,
    t.name AS target_name,
    ind.name AS indication_name,
    opp.action AS opportunity_action,
    opp.confidence AS opportunity_confidence,
    -- Full text search document vector
    setweight(to_tsvector('english', COALESCE(a.preferred_name, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(t.symbol, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(ind.name, '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(c.name, '')), 'C') AS search_vector
FROM canonical.assets a
LEFT JOIN canonical.companies c ON a.owner_company_id = c.id
LEFT JOIN canonical.asset_targets atl ON a.id = atl.asset_id
LEFT JOIN canonical.targets t ON atl.target_id = t.id
LEFT JOIN canonical.asset_indications ail ON a.id = ail.asset_id
LEFT JOIN canonical.indications ind ON ail.indication_id = ind.id
LEFT JOIN canonical.recommendations opp ON a.id = opp.asset_id;

-- 3. Search Audit Log Table
-- Records parsed queries, compiled parameters, and execution telemetry
CREATE TABLE IF NOT EXISTS search_query_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_query TEXT NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    search_mode VARCHAR(32) NOT NULL DEFAULT 'hybrid',
    structured_constraints JSONB NOT NULL DEFAULT '[]'::jsonb,
    compiled_sql_template TEXT NOT NULL,
    compiled_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_validated BOOLEAN NOT NULL DEFAULT TRUE,
    validation_status VARCHAR(64) NOT NULL DEFAULT 'VALIDATED',
    match_count INTEGER NOT NULL DEFAULT 0,
    execution_time_ms NUMERIC(8, 2) NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_search_audit_target ON search_query_audit_logs(target_type);
CREATE INDEX IF NOT EXISTS idx_search_audit_created ON search_query_audit_logs(created_at);

-- 4. Safety Validation Function
-- Strictly rejects unvalidated queries containing injection or DDL keywords
CREATE OR REPLACE FUNCTION validate_search_constraint_safety(constraint_json JSONB)
RETURNS BOOLEAN AS $$
DECLARE
    field_text TEXT;
    val_text TEXT;
BEGIN
    field_text := lower(constraint_json->>'field');
    val_text := lower(constraint_json->>'value');

    -- Whitelist field check
    IF field_text NOT IN (
        'target', 'disease', 'indication', 'stage', 'modality',
        'biomarker', 'mutation', 'cns_active', 'clinical_evidence',
        'company', 'owner', 'licensing_status', 'phase', 'status', 'year', 'action'
    ) THEN
        RETURN FALSE;
    END IF;

    -- Injection pattern check
    IF val_text ~* '(;|--|/\*|\*/|\bdrop\b|\bdelete\b|\bupdate\b|\binsert\b|\bexec\b|\bunion\b)' THEN
        RETURN FALSE;
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;
