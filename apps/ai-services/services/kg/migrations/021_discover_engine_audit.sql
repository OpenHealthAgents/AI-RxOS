-- ==============================================================================
-- Migration: 021_discover_engine_audit.sql
-- Description: Discover Engine Audit & Search Lineage Schema
-- Stores natural language search queries, parsed 14-dimensional structured filters,
-- execution metrics, and ranked asset lineage.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS discover_queries_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    natural_language_query TEXT NOT NULL,
    parsed_filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    results_count INTEGER NOT NULL DEFAULT 0,
    top_matched_asset_ids UUID[] NOT NULL DEFAULT '{}',
    execution_latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discover_audit_created ON discover_queries_audit (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_discover_audit_query ON discover_queries_audit USING gin(to_tsvector('english', natural_language_query));
