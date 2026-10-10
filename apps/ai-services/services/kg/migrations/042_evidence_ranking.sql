-- ==============================================================================
-- Migration: 042_evidence_ranking.sql
-- Description: Schema and analytical views for 9-dimension evidence ranking
--
-- Ranking dimensions:
--   1. source quality
--   2. directness
--   3. recency
--   4. human relevance
--   5. study design
--   6. sample size
--   7. peer review
--   8. confidence
--   9. temporal validity
-- ==============================================================================

-- 1. Evidence Ranking Cache & Telemetry Table
CREATE TABLE IF NOT EXISTS evidence_rankings_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID,
    evidence_id UUID NOT NULL,
    ranking INTEGER NOT NULL,
    composite_rank_score NUMERIC(5, 2) NOT NULL CHECK (composite_rank_score >= 0.0 AND composite_rank_score <= 100.0),
    ranking_tier VARCHAR(32) NOT NULL CHECK (
        ranking_tier IN (
            'TIER_1_PINNACLE',
            'TIER_2_HIGH',
            'TIER_3_MODERATE',
            'TIER_4_LOW',
            'TIER_5_INSUFFICIENT'
        )
    ),
    calibrated_confidence NUMERIC(4, 3) NOT NULL CHECK (calibrated_confidence >= 0.0 AND calibrated_confidence <= 1.0),
    is_temporally_valid BOOLEAN NOT NULL DEFAULT TRUE,
    dimension_scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    ranking_rationale TEXT NOT NULL,
    key_strengths TEXT[] NOT NULL DEFAULT '{}',
    limitations TEXT[] NOT NULL DEFAULT '{}',
    as_of_date DATE NOT NULL DEFAULT CURRENT_DATE,
    prediction_cutoff DATE,
    ranked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_rankings_asset ON evidence_rankings_log (asset_id);
CREATE INDEX IF NOT EXISTS idx_evidence_rankings_evidence ON evidence_rankings_log (evidence_id);
CREATE INDEX IF NOT EXISTS idx_evidence_rankings_score ON evidence_rankings_log (composite_rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_evidence_rankings_tier ON evidence_rankings_log (ranking_tier);

-- 2. Ranked Evidence Analytical View
CREATE OR REPLACE VIEW view_ranked_evidence_overview AS
SELECT
    erl.id AS ranking_id,
    erl.asset_id,
    erl.evidence_id,
    erl.ranking,
    erl.composite_rank_score,
    erl.ranking_tier,
    erl.calibrated_confidence,
    erl.is_temporally_valid,
    erl.ranking_rationale,
    erl.as_of_date,
    erl.prediction_cutoff,
    s.title AS source_title,
    s.source_type,
    s.publication_date
FROM evidence_rankings_log erl
LEFT JOIN evidence_sources s ON erl.evidence_id = s.id;
