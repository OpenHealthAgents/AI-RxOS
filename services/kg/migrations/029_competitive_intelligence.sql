-- ==============================================================================
-- Migration: 029_competitive_intelligence.sql
-- Description: Competitive Intelligence Engine Schema
-- For every asset identifies competitors across:
-- direct competitors, same target, same mechanism, same biomarker, same indication,
-- same patient population, same modality, clinical-stage competitors,
-- approved standards of care, and emerging academic programs.
-- Compares across 11 dimensions:
-- potency, selectivity, CNS, clinical stage, efficacy, safety, biomarker,
-- resistance, combination, ownership, and commercial opportunity.
-- Produces:
-- Competitive Density, Differentiation Score, Competitive Risk, White-Space Opportunity.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS competitive_intelligence_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id VARCHAR(64) NOT NULL UNIQUE,
    asset_name VARCHAR(128) NOT NULL,
    target VARCHAR(64) NOT NULL,
    primary_indication VARCHAR(128) NOT NULL,
    patient_population VARCHAR(256) NOT NULL,
    modality VARCHAR(64) NOT NULL,
    stage VARCHAR(64) NOT NULL,
    competitive_density_score DOUBLE PRECISION NOT NULL,
    competitive_density_tier VARCHAR(32) NOT NULL,
    differentiation_score DOUBLE PRECISION NOT NULL,
    differentiation_tier VARCHAR(32) NOT NULL,
    competitive_risk_score DOUBLE PRECISION NOT NULL,
    competitive_risk_tier VARCHAR(32) NOT NULL,
    cohort_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    head_to_head_comparisons JSONB NOT NULL DEFAULT '[]'::jsonb,
    white_space_opportunities JSONB NOT NULL DEFAULT '[]'::jsonb,
    evidence_citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_comp_intel_asset ON competitive_intelligence_profiles (asset_id);
CREATE INDEX IF NOT EXISTS idx_comp_intel_target ON competitive_intelligence_profiles (target);
CREATE INDEX IF NOT EXISTS idx_comp_intel_density ON competitive_intelligence_profiles (competitive_density_score);
CREATE INDEX IF NOT EXISTS idx_comp_intel_diff ON competitive_intelligence_profiles (differentiation_score);
CREATE INDEX IF NOT EXISTS idx_comp_intel_risk ON competitive_intelligence_profiles (competitive_risk_score);

CREATE TABLE IF NOT EXISTS competitor_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    competitor_id VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    target VARCHAR(64) NOT NULL,
    mechanism VARCHAR(128) NOT NULL,
    modality VARCHAR(64) NOT NULL,
    stage VARCHAR(64) NOT NULL,
    is_approved_soc BOOLEAN NOT NULL DEFAULT FALSE,
    is_clinical_stage BOOLEAN NOT NULL DEFAULT FALSE,
    is_emerging_academic BOOLEAN NOT NULL DEFAULT FALSE,
    sponsor_or_owner VARCHAR(128) NOT NULL,
    indications JSONB NOT NULL DEFAULT '[]'::jsonb,
    biomarkers JSONB NOT NULL DEFAULT '[]'::jsonb,
    patient_populations JSONB NOT NULL DEFAULT '[]'::jsonb,
    comparison_metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_competitor_id ON competitor_entities (competitor_id);
CREATE INDEX IF NOT EXISTS idx_competitor_target ON competitor_entities (target);
CREATE INDEX IF NOT EXISTS idx_competitor_stage ON competitor_entities (stage);
CREATE INDEX IF NOT EXISTS idx_competitor_soc ON competitor_entities (is_approved_soc);
