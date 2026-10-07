-- ==============================================================================
-- Migration: 033_contradictory_evidence.sql
-- Description: Contradictory Evidence & Disagreement Adjudication Schema
-- Core Epistemic Invariant: If two credible sources disagree, do not silently select one.
-- Represents:
-- - claim A
-- - claim B
-- - sources (source A, source B)
-- - dates (date A, date B)
-- - study design (design A, design B)
-- - quality (quality score A, quality score B)
-- - confidence (confidence A, confidence B)
-- - possible explanation (mechanistic, cohort, assay, or dosage rationale)
-- Supports polarities:
-- - SUPPORTING
-- - CONTRADICTORY
-- - NEUTRAL
-- - UNKNOWN
-- ==============================================================================

CREATE TABLE IF NOT EXISTS contradiction_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    topic VARCHAR(255) NOT NULL,
    parameter_name VARCHAR(255) NOT NULL,
    category VARCHAR(64) NOT NULL CHECK (
        category IN (
            'efficacy_divergence',
            'safety_toxicity_conflict',
            'cns_penetration_discrepancy',
            'resistance_emergence_divergence',
            'selectivity_margin_dispute',
            'biomarker_stratification_discordance'
        )
    ),
    status VARCHAR(64) NOT NULL DEFAULT 'unresolved_dispute' CHECK (
        status IN (
            'unresolved_dispute',
            'partially_explained',
            'resolved_by_superior_design',
            'under_active_investigation'
        )
    ),
    -- Claim A Details
    claim_a_id UUID NOT NULL,
    claim_a_text TEXT NOT NULL,
    claim_a_polarity VARCHAR(32) NOT NULL CHECK (
        claim_a_polarity IN ('SUPPORTING', 'CONTRADICTING', 'CONTRADICTORY', 'NEUTRAL', 'UNKNOWN')
    ),
    claim_a_source_id UUID NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    claim_a_date DATE NOT NULL,
    claim_a_study_design VARCHAR(64) NOT NULL,
    claim_a_quality_score NUMERIC(5, 2) NOT NULL CHECK (claim_a_quality_score >= 0.0 AND claim_a_quality_score <= 100.0),
    claim_a_confidence NUMERIC(4, 3) NOT NULL CHECK (claim_a_confidence >= 0.0 AND claim_a_confidence <= 1.0),
    claim_a_measurement VARCHAR(255),
    claim_a_sample_size INTEGER,

    -- Claim B Details
    claim_b_id UUID NOT NULL,
    claim_b_text TEXT NOT NULL,
    claim_b_polarity VARCHAR(32) NOT NULL CHECK (
        claim_b_polarity IN ('SUPPORTING', 'CONTRADICTING', 'CONTRADICTORY', 'NEUTRAL', 'UNKNOWN')
    ),
    claim_b_source_id UUID NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    claim_b_date DATE NOT NULL,
    claim_b_study_design VARCHAR(64) NOT NULL,
    claim_b_quality_score NUMERIC(5, 2) NOT NULL CHECK (claim_b_quality_score >= 0.0 AND claim_b_quality_score <= 100.0),
    claim_b_confidence NUMERIC(4, 3) NOT NULL CHECK (claim_b_confidence >= 0.0 AND claim_b_confidence <= 1.0),
    claim_b_measurement VARCHAR(255),
    claim_b_sample_size INTEGER,

    -- Discrepancy Analysis & Explanations
    possible_explanation TEXT NOT NULL,
    epistemic_warning TEXT NOT NULL,
    resolution_recommendation TEXT NOT NULL,
    quality_delta NUMERIC(5, 2) NOT NULL,
    confidence_delta NUMERIC(4, 3) NOT NULL,

    -- Metadata & Invariant Enforcements
    silent_selection_prevented BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_contradiction_asset_id ON contradiction_records (asset_id);
CREATE INDEX IF NOT EXISTS idx_contradiction_category ON contradiction_records (category);
CREATE INDEX IF NOT EXISTS idx_contradiction_status ON contradiction_records (status);
CREATE INDEX IF NOT EXISTS idx_contradiction_param ON contradiction_records (parameter_name);
