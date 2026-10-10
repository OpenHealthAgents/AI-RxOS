-- ==============================================================================
-- Migration: 028_safety_intelligence.sql
-- Description: Safety Intelligence Engine Schema
-- Captures 10 safety and toxicity dimensions:
-- common adverse events, Grade >=3 adverse events, dose-limiting toxicity,
-- discontinuation, organ toxicity, target-related toxicity, off-target toxicity,
-- animal toxicity, therapeutic window, and dose exposure relationship.
-- Produces:
-- Safety Score, Therapeutic Index Score, Safety Confidence, Major Risk Signals.
-- Ratings: GOOD, MODERATE, HIGH RISK, INSUFFICIENT EVIDENCE.
-- Strict Invariant: Do not convert missing safety evidence into a positive score.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS safety_intelligence_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL UNIQUE,
    asset_name VARCHAR(128) NOT NULL,
    safety_rating VARCHAR(32) NOT NULL,
    safety_score DOUBLE PRECISION NOT NULL,
    therapeutic_index_score DOUBLE PRECISION NOT NULL,
    safety_confidence DOUBLE PRECISION NOT NULL,
    major_risk_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    common_adverse_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    grade_3_plus_adverse_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    dose_limiting_toxicity JSONB NOT NULL DEFAULT '{}'::jsonb,
    discontinuation JSONB NOT NULL DEFAULT '{}'::jsonb,
    organ_toxicities JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_related_toxicity JSONB NOT NULL DEFAULT '{}'::jsonb,
    off_target_toxicity JSONB NOT NULL DEFAULT '{}'::jsonb,
    animal_toxicity JSONB NOT NULL DEFAULT '{}'::jsonb,
    therapeutic_window JSONB NOT NULL DEFAULT '{}'::jsonb,
    dose_exposure_relationship JSONB NOT NULL DEFAULT '{}'::jsonb,
    has_missing_evidence BOOLEAN NOT NULL DEFAULT FALSE,
    missing_evidence_details JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    epistemic_audit JSONB NOT NULL DEFAULT '{}'::jsonb,
    disclaimer TEXT NOT NULL DEFAULT 'Do not convert missing safety evidence into a positive score. Absence of documented toxicity evidence does not constitute safety.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_safety_intel_asset ON safety_intelligence_profiles (asset_id);
CREATE INDEX IF NOT EXISTS idx_safety_intel_rating ON safety_intelligence_profiles (safety_rating);
CREATE INDEX IF NOT EXISTS idx_safety_intel_score ON safety_intelligence_profiles (safety_score);

CREATE TABLE IF NOT EXISTS safety_adverse_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL,
    term VARCHAR(128) NOT NULL,
    system_organ_class VARCHAR(64) NOT NULL,
    any_grade_pct DOUBLE PRECISION,
    grade_3_plus_pct DOUBLE PRECISION,
    is_dose_limiting BOOLEAN NOT NULL DEFAULT FALSE,
    is_target_related BOOLEAN NOT NULL DEFAULT FALSE,
    source_citation TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_safety_ae_asset ON safety_adverse_events (asset_id);
CREATE INDEX IF NOT EXISTS idx_safety_ae_term ON safety_adverse_events (term);
CREATE INDEX IF NOT EXISTS idx_safety_ae_soc ON safety_adverse_events (system_organ_class);
