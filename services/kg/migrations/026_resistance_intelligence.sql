-- ==============================================================================
-- Migration: 026_resistance_intelligence.sql
-- Description: Resistance Intelligence Engine Schema
-- Stores asset escape mechanisms across 8 molecular categories, epistemic
-- classification (Clinically observed, Observed, Preclinical, Mechanistically
-- inferred, AI-predicted), resistance risk profiles, and potential interventions.
-- Strict Invariant: Never present predicted resistance as experimentally proven.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS resistance_escape_mechanisms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    mechanism_name VARCHAR(256) NOT NULL,
    category VARCHAR(64) NOT NULL,
    classification VARCHAR(64) NOT NULL,
    is_known_mechanism BOOLEAN NOT NULL DEFAULT TRUE,
    is_experimentally_proven BOOLEAN NOT NULL DEFAULT FALSE,
    frequency_pct DOUBLE PRECISION,
    impact_severity VARCHAR(32) NOT NULL,
    molecular_description TEXT NOT NULL,
    potential_intervention JSONB NOT NULL DEFAULT '{}'::jsonb,
    evidence_citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL,
    epistemic_status_note TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_res_escape_asset ON resistance_escape_mechanisms (asset_id);
CREATE INDEX IF NOT EXISTS idx_res_escape_category ON resistance_escape_mechanisms (category);
CREATE INDEX IF NOT EXISTS idx_res_escape_classification ON resistance_escape_mechanisms (classification);
CREATE INDEX IF NOT EXISTS idx_res_escape_proven ON resistance_escape_mechanisms (is_experimentally_proven);

CREATE TABLE IF NOT EXISTS resistance_risk_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL UNIQUE,
    asset_name VARCHAR(128) NOT NULL,
    overall_risk_score DOUBLE PRECISION NOT NULL,
    risk_tier VARCHAR(32) NOT NULL,
    primary_vulnerability TEXT NOT NULL,
    top_escape_mechanisms JSONB NOT NULL DEFAULT '[]'::jsonb,
    mechanisms_by_category JSONB NOT NULL DEFAULT '{}'::jsonb,
    potential_interventions JSONB NOT NULL DEFAULT '[]'::jsonb,
    epistemic_audit JSONB NOT NULL DEFAULT '{}'::jsonb,
    disclaimer TEXT NOT NULL DEFAULT 'Never present predicted resistance as experimentally proven resistance. Predicted mechanisms represent hypothesis-generation for prospective surveillance.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_res_profile_asset ON resistance_risk_profiles (asset_id);
CREATE INDEX IF NOT EXISTS idx_res_profile_risk_tier ON resistance_risk_profiles (risk_tier);
