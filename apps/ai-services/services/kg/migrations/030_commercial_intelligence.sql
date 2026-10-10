-- ==============================================================================
-- Migration: 030_commercial_intelligence.sql
-- Description: Commercial Opportunity Intelligence Engine Schema
-- Evaluates 11 dimensions:
-- addressable population, biomarker-defined population, treatment duration,
-- standard of care, unmet need, competitive density, clinical differentiation,
-- potential line of therapy, pricing analogs, pipeline crowding, and market expansion.
-- Produces:
-- Commercial Opportunity Score, Market Attractiveness, Competitive Pressure,
-- Unmet Need, and Commercial Confidence.
-- Strict Epistemic Invariants:
-- Do not fabricate market size. Every commercial assumption must identify provenance:
-- OBSERVED, EXTERNALLY_SOURCED, MODELED, ASSUMED, or UNKNOWN.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS commercial_opportunity_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL UNIQUE,
    asset_name VARCHAR(128) NOT NULL,
    indication VARCHAR(128) NOT NULL,
    target VARCHAR(64) NOT NULL,
    potential_line_of_therapy VARCHAR(64) NOT NULL,
    commercial_opportunity_score DOUBLE PRECISION NOT NULL,
    market_attractiveness_tier VARCHAR(32) NOT NULL,
    market_attractiveness_score DOUBLE PRECISION NOT NULL,
    competitive_pressure_tier VARCHAR(32) NOT NULL,
    competitive_pressure_score DOUBLE PRECISION NOT NULL,
    unmet_need_tier VARCHAR(32) NOT NULL,
    unmet_need_score DOUBLE PRECISION NOT NULL,
    commercial_confidence DOUBLE PRECISION NOT NULL,
    epidemiology_and_population JSONB NOT NULL DEFAULT '{}'::jsonb,
    treatment_and_pricing JSONB NOT NULL DEFAULT '{}'::jsonb,
    competitive_and_market_dynamics JSONB NOT NULL DEFAULT '{}'::jsonb,
    expansion_opportunities JSONB NOT NULL DEFAULT '[]'::jsonb,
    assumptions_audit JSONB NOT NULL DEFAULT '[]'::jsonb,
    disclaimer TEXT NOT NULL DEFAULT 'Do not fabricate market size. IP, clinical, and pricing intelligence does not constitute forward revenue guarantees. Projections reflect explicit mathematical derivations with declared assumption provenance.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comm_opp_asset ON commercial_opportunity_profiles (asset_id);
CREATE INDEX IF NOT EXISTS idx_comm_opp_score ON commercial_opportunity_profiles (commercial_opportunity_score);
CREATE INDEX IF NOT EXISTS idx_comm_opp_attract ON commercial_opportunity_profiles (market_attractiveness_tier);
CREATE INDEX IF NOT EXISTS idx_comm_opp_unmet ON commercial_opportunity_profiles (unmet_need_tier);

CREATE TABLE IF NOT EXISTS commercial_assumptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    assumption_key VARCHAR(128) NOT NULL,
    parameter_value VARCHAR(256) NOT NULL,
    provenance VARCHAR(32) NOT NULL,
    source_citation TEXT,
    methodology TEXT,
    confidence DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comm_assump_asset ON commercial_assumptions (asset_id);
CREATE INDEX IF NOT EXISTS idx_comm_assump_prov ON commercial_assumptions (provenance);
CREATE INDEX IF NOT EXISTS idx_comm_assump_key ON commercial_assumptions (assumption_key);
