-- ==============================================================================
-- Migration: 036_pubmed_production_lineage_and_quality.sql
-- Description: Production PubMed Ingestion, Lineage, Quality & Groundedness
-- ==============================================================================

-- 1. Add evidence_source_id and mesh column to pubmed_raw_articles
ALTER TABLE pubmed_raw_articles
    ADD COLUMN IF NOT EXISTS evidence_source_id UUID,
    ADD COLUMN IF NOT EXISTS mesh TEXT[] DEFAULT '{}';

-- 2. Add lineage and entity resolution columns to pubmed_extracted_observations
ALTER TABLE pubmed_extracted_observations
    ADD COLUMN IF NOT EXISTS lineage_id UUID DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS provenance_hash VARCHAR(64),
    ADD COLUMN IF NOT EXISTS evidence_source_id UUID,
    ADD COLUMN IF NOT EXISTS resolved_canonical_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS entity_resolution_confidence NUMERIC(4, 3),
    ADD COLUMN IF NOT EXISTS resolution_method VARCHAR(64);

-- 3. Extend check constraint on extraction_category if desired
ALTER TABLE pubmed_extracted_observations
    DROP CONSTRAINT IF EXISTS pubmed_extracted_observations_extraction_category_check;

ALTER TABLE pubmed_extracted_observations
    ADD CONSTRAINT pubmed_extracted_observations_extraction_category_check CHECK (
        extraction_category IN (
            'asset', 'drug', 'target', 'gene', 'mutation', 'disease', 'biomarker',
            'model', 'cell_line', 'animal_model', 'efficacy', 'toxicity',
            'cns', 'cns_exposure', 'cns_efficacy', 'resistance', 'combination',
            'clinical_result', 'clinical_outcome'
        )
    );

-- 4. Quality Reports Table
CREATE TABLE IF NOT EXISTS pubmed_quality_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid VARCHAR(64) NOT NULL UNIQUE REFERENCES pubmed_raw_articles(pmid) ON DELETE CASCADE,
    overall_quality_score NUMERIC(5, 2) NOT NULL,
    quality_tier VARCHAR(32) NOT NULL CHECK (quality_tier IN ('HIGH', 'MEDIUM', 'LOW', 'REJECTED')),
    quality_passed BOOLEAN NOT NULL DEFAULT TRUE,
    hallucination_check_passed BOOLEAN NOT NULL DEFAULT TRUE,
    rules JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pubmed_quality_pmid ON pubmed_quality_reports (pmid);
CREATE INDEX IF NOT EXISTS idx_pubmed_quality_tier ON pubmed_quality_reports (quality_tier);
CREATE INDEX IF NOT EXISTS idx_pubmed_obs_lineage ON pubmed_extracted_observations (lineage_id);
