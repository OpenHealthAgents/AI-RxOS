-- ==============================================================================
-- Migration: 025_patient_match_intelligence.sql
-- Description: PatientMatch Population Intelligence Engine Schema
-- Stores asset-centric patient population profiles (Best, Secondary, Excluded),
-- biomarker strategies, and scenario-based cohort match evaluations.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS patient_population_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    asset_name VARCHAR(128) NOT NULL,
    best_population JSONB NOT NULL DEFAULT '{}'::jsonb,
    secondary_population JSONB NOT NULL DEFAULT '{}'::jsonb,
    excluded_population JSONB NOT NULL DEFAULT '{}'::jsonb,
    biomarker_strategy JSONB NOT NULL DEFAULT '{}'::jsonb,
    patient_match_score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    mechanistic_rationale TEXT NOT NULL,
    disclaimer TEXT NOT NULL DEFAULT 'Do not make patient-specific medical recommendations. This is drug-development population intelligence.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patient_pop_asset ON patient_population_profiles (asset_id);

CREATE TABLE IF NOT EXISTS patient_match_scenario_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    best_matched_asset_id VARCHAR(64) NOT NULL,
    match_score DOUBLE PRECISION NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    matched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_match_audit_time ON patient_match_scenario_audits (matched_at DESC);
