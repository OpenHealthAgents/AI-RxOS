-- ==============================================================================
-- Migration: 022_biology_intelligence.sql
-- Description: Biology Intelligence Engine Schema
-- Stores raw biological observations (IC50, selectivity ratios, CRISPR dependencies,
-- animal efficacy, patient-derived models, clinical response) and derived
-- Biology Intelligence Profile evaluation snapshots with explicit formula lineage.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS biology_raw_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    parameter_name VARCHAR(128) NOT NULL,
    observation_type VARCHAR(64) NOT NULL,
    raw_text_value TEXT NOT NULL,
    normalized_value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(32),
    assay_type VARCHAR(128),
    target_or_gene VARCHAR(64),
    model_system VARCHAR(128),
    source_citation TEXT NOT NULL,
    source_url TEXT,
    pmid VARCHAR(32),
    nct_id VARCHAR(32),
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    observation_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bio_obs_asset ON biology_raw_observations (asset_id);
CREATE INDEX IF NOT EXISTS idx_bio_obs_param ON biology_raw_observations (parameter_name);
CREATE INDEX IF NOT EXISTS idx_bio_obs_type ON biology_raw_observations (observation_type);

CREATE TABLE IF NOT EXISTS biology_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    biology_validation_score DOUBLE PRECISION NOT NULL,
    potency_score DOUBLE PRECISION NOT NULL,
    selectivity_score DOUBLE PRECISION NOT NULL,
    biomarker_score DOUBLE PRECISION NOT NULL,
    mechanistic_confidence DOUBLE PRECISION NOT NULL,
    translational_readiness DOUBLE PRECISION NOT NULL,
    dimension_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    lineage_provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_observation_ids UUID[] NOT NULL DEFAULT '{}',
    unknowns TEXT[] NOT NULL DEFAULT '{}',
    overall_confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bio_eval_asset ON biology_evaluations (asset_id);
CREATE INDEX IF NOT EXISTS idx_bio_eval_time ON biology_evaluations (evaluated_at DESC);
