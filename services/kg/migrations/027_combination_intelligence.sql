-- ==============================================================================
-- Migration: 027_combination_intelligence.sql
-- Description: Combination Intelligence Engine Schema
-- Evaluates therapeutic combinations addressing specific resistance mechanisms.
-- Captures 8 evaluation dimensions: mechanistic complementarity, preclinical evidence,
-- clinical evidence, toxicity overlap, pharmacological feasibility, development feasibility,
-- existing combinations, and competitive combinations.
-- Strict Invariant: Clearly distinguish clinically validated, preclinical supported,
-- mechanistically plausible, and AI-generated hypotheses.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS combination_strategies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resistance_mechanism_id VARCHAR(64),
    resistance_mechanism_name VARCHAR(256) NOT NULL,
    primary_asset_id VARCHAR(64) NOT NULL,
    primary_asset_name VARCHAR(128) NOT NULL,
    partner_name VARCHAR(128) NOT NULL,
    partner_class VARCHAR(128) NOT NULL,
    regimen_name VARCHAR(256) NOT NULL,
    validation_status VARCHAR(64) NOT NULL,
    is_clinically_validated BOOLEAN NOT NULL DEFAULT FALSE,
    mechanistic_complementarity JSONB NOT NULL DEFAULT '{}'::jsonb,
    preclinical_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    clinical_evidence JSONB NOT NULL DEFAULT '{}'::jsonb,
    toxicity_overlap JSONB NOT NULL DEFAULT '{}'::jsonb,
    pharmacological_feasibility JSONB NOT NULL DEFAULT '{}'::jsonb,
    development_feasibility JSONB NOT NULL DEFAULT '{}'::jsonb,
    existing_combinations JSONB NOT NULL DEFAULT '[]'::jsonb,
    competitive_combinations JSONB NOT NULL DEFAULT '[]'::jsonb,
    rationale TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    development_risk_score DOUBLE PRECISION NOT NULL,
    development_risk_tier VARCHAR(32) NOT NULL,
    evidence_citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    disclaimer TEXT NOT NULL DEFAULT 'Never present an AI-generated hypothesis or mechanistically plausible combination as clinically validated. Clinical safety and efficacy must be established empirically.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comb_strat_primary ON combination_strategies (primary_asset_id);
CREATE INDEX IF NOT EXISTS idx_comb_strat_partner ON combination_strategies (partner_name);
CREATE INDEX IF NOT EXISTS idx_comb_strat_mech ON combination_strategies (resistance_mechanism_name);
CREATE INDEX IF NOT EXISTS idx_comb_strat_status ON combination_strategies (validation_status);
CREATE INDEX IF NOT EXISTS idx_comb_strat_risk ON combination_strategies (development_risk_tier);

CREATE TABLE IF NOT EXISTS combination_intelligence_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    query_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    recommended_combinations JSONB NOT NULL DEFAULT '[]'::jsonb,
    epistemic_audit JSONB NOT NULL DEFAULT '{}'::jsonb,
    disclaimer TEXT NOT NULL DEFAULT 'Never present an AI-generated hypothesis or mechanistically plausible combination as clinically validated.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comb_eval_asset ON combination_intelligence_evaluations (asset_id);
