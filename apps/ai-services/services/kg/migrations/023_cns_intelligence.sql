-- ==============================================================================
-- Migration: 023_cns_intelligence.sql
-- Description: CNS Intelligence Engine Schema
-- Stores raw empirical CNS observations (brain/plasma ratio Kp, Kp,uu, CSF exposure,
-- unbound brain concentration, BBB penetration, brain tumor exposure, intracranial response,
-- CNS progression, brain metastasis response) normalized across species and conditions,
-- and derived CNS intelligence profile evaluations with full formula lineage.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS cns_raw_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    parameter_name VARCHAR(128) NOT NULL,
    evidence_level VARCHAR(64) NOT NULL,
    species VARCHAR(64) NOT NULL,
    experimental_condition TEXT,
    raw_text_value TEXT NOT NULL,
    normalized_value DOUBLE PRECISION NOT NULL,
    normalized_unit VARCHAR(32),
    source_citation TEXT NOT NULL,
    source_url TEXT,
    pmid VARCHAR(32),
    nct_id VARCHAR(32),
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    observation_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cns_obs_asset ON cns_raw_observations (asset_id);
CREATE INDEX IF NOT EXISTS idx_cns_obs_param ON cns_raw_observations (parameter_name);
CREATE INDEX IF NOT EXISTS idx_cns_obs_level ON cns_raw_observations (evidence_level);
CREATE INDEX IF NOT EXISTS idx_cns_obs_species ON cns_raw_observations (species);

CREATE TABLE IF NOT EXISTS cns_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    cns_exposure_score DOUBLE PRECISION NOT NULL,
    cns_activity_score DOUBLE PRECISION NOT NULL,
    cns_translational_confidence DOUBLE PRECISION NOT NULL,
    normalized_parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_level_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    formula_lineages JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_observation_ids UUID[] NOT NULL DEFAULT '{}',
    unknowns TEXT[] NOT NULL DEFAULT '{}',
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cns_eval_asset ON cns_evaluations (asset_id);
CREATE INDEX IF NOT EXISTS idx_cns_eval_time ON cns_evaluations (evaluated_at DESC);
