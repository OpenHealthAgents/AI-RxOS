-- ==============================================================================
-- Migration: 032_evidence_quality_scoring.sql
-- Description: Rigorous 10-Dimension Evidence Quality Evaluation Schema
-- Evaluates:
-- 1. peer review
-- 2. study design
-- 3. sample size
-- 4. model relevance
-- 5. human evidence
-- 6. prospective design
-- 7. replication
-- 8. source quality
-- 9. directness
-- 10. recency
-- Enforces epistemic invariant: Never convert low evidence into high-confidence claims.
-- Exposes: quality, confidence, and transparent limitations.
-- ==============================================================================

-- 1. Evidence Quality Appraisals
CREATE TABLE IF NOT EXISTS evidence_quality_appraisals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    overall_quality_score NUMERIC(5, 2) NOT NULL CHECK (overall_quality_score >= 0.0 AND overall_quality_score <= 100.0),
    quality_grade VARCHAR(32) NOT NULL CHECK (
        quality_grade IN (
            'GRADE_A_HIGH',
            'GRADE_B_MODERATE',
            'GRADE_C_LOW',
            'GRADE_D_VERY_LOW'
        )
    ),
    calibrated_confidence NUMERIC(4, 3) NOT NULL CHECK (calibrated_confidence >= 0.0 AND calibrated_confidence <= 1.0),
    confidence_level VARCHAR(32) NOT NULL CHECK (
        confidence_level IN (
            'very_high',
            'high',
            'medium',
            'low',
            'insufficient'
        )
    ),
    peer_review_score NUMERIC(5, 2) NOT NULL,
    study_design_score NUMERIC(5, 2) NOT NULL,
    sample_size_score NUMERIC(5, 2) NOT NULL,
    model_relevance_score NUMERIC(5, 2) NOT NULL,
    human_evidence_score NUMERIC(5, 2) NOT NULL,
    prospective_design_score NUMERIC(5, 2) NOT NULL,
    replication_score NUMERIC(5, 2) NOT NULL,
    source_quality_score NUMERIC(5, 2) NOT NULL,
    directness_score NUMERIC(5, 2) NOT NULL,
    recency_score NUMERIC(5, 2) NOT NULL,
    dimension_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    scoring_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    limitations TEXT[] NOT NULL DEFAULT '{}',
    is_high_confidence_claim_allowed BOOLEAN NOT NULL DEFAULT TRUE,
    epistemic_warning TEXT,
    appraised_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_appraisal_source_id ON evidence_quality_appraisals (source_id);
CREATE INDEX IF NOT EXISTS idx_appraisal_grade ON evidence_quality_appraisals (quality_grade);
CREATE INDEX IF NOT EXISTS idx_appraisal_confidence ON evidence_quality_appraisals (confidence_level);
CREATE INDEX IF NOT EXISTS idx_appraisal_gate ON evidence_quality_appraisals (is_high_confidence_claim_allowed);

-- 2. Claim Epistemic Safety Audits
CREATE TABLE IF NOT EXISTS claim_epistemic_audits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID REFERENCES evidence_claims(id) ON DELETE CASCADE,
    appraisal_id UUID REFERENCES evidence_quality_appraisals(id) ON DELETE CASCADE,
    claimed_confidence NUMERIC(4, 3) NOT NULL,
    evidence_quality_score NUMERIC(5, 2) NOT NULL,
    is_conversion_allowed BOOLEAN NOT NULL,
    audit_passed BOOLEAN NOT NULL,
    violation_reason TEXT,
    audited_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claim_audit_claim_id ON claim_epistemic_audits (claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_audit_passed ON claim_epistemic_audits (audit_passed);
