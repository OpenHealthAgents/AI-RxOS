-- ==============================================================================
-- Migration: 024_clinical_intelligence.sql
-- Description: Clinical Development Intelligence Engine Schema
-- Stores trial evaluations (stage, trial design, enrollment, population,
-- biomarker enrichment, endpoint quality, ORR, CR, DOR, PFS, OS, toxicities,
-- dose optimization, execution) and overall clinical intelligence profiles
-- with strict separation of observed outcomes, model predictions, expert
-- interpretations, and unknowns.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS clinical_trials_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    trial_id VARCHAR(64) NOT NULL,
    trial_title TEXT NOT NULL,
    stage VARCHAR(32) NOT NULL,
    trial_design JSONB NOT NULL DEFAULT '{}'::jsonb,
    enrollment INTEGER NOT NULL DEFAULT 0,
    population_selection TEXT NOT NULL,
    biomarker_enrichment JSONB NOT NULL DEFAULT '{}'::jsonb,
    endpoint_quality JSONB NOT NULL DEFAULT '{}'::jsonb,
    observed_outcomes JSONB NOT NULL DEFAULT '{}'::jsonb,
    safety_toxicities JSONB NOT NULL DEFAULT '{}'::jsonb,
    dose_optimization JSONB NOT NULL DEFAULT '{}'::jsonb,
    trial_execution JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clin_trials_asset ON clinical_trials_evaluations (asset_id);
CREATE INDEX IF NOT EXISTS idx_clin_trials_id ON clinical_trials_evaluations (trial_id);
CREATE INDEX IF NOT EXISTS idx_clin_trials_stage ON clinical_trials_evaluations (stage);

CREATE TABLE IF NOT EXISTS clinical_intelligence_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    clinical_success_probability DOUBLE PRECISION NOT NULL,
    clinical_readiness_score DOUBLE PRECISION NOT NULL,
    development_risk_score DOUBLE PRECISION NOT NULL,
    evidence_confidence DOUBLE PRECISION NOT NULL,
    observed_clinical_outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
    model_predictions JSONB NOT NULL DEFAULT '[]'::jsonb,
    expert_interpretations JSONB NOT NULL DEFAULT '[]'::jsonb,
    unknowns TEXT[] NOT NULL DEFAULT '{}',
    formula_lineages JSONB NOT NULL DEFAULT '{}'::jsonb,
    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clin_eval_asset ON clinical_intelligence_evaluations (asset_id);
CREATE INDEX IF NOT EXISTS idx_clin_eval_time ON clinical_intelligence_evaluations (evaluated_at DESC);
