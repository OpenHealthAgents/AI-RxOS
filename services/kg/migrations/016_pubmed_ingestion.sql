-- ==============================================================================
-- Migration: 016_pubmed_ingestion.sql
-- Description: Production-Quality PubMed Ingestion and 16-Domain Observation Storage
-- Captures raw sources, full provenance, and explicitly distinguishes AI inferences from ground truth.
-- ==============================================================================

-- 1. Raw PubMed Articles
CREATE TABLE IF NOT EXISTS pubmed_raw_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid VARCHAR(64) NOT NULL UNIQUE,
    doi VARCHAR(255),
    title TEXT NOT NULL,
    abstract TEXT NOT NULL,
    authors TEXT[] NOT NULL DEFAULT '{}',
    journal VARCHAR(255) NOT NULL,
    publication_date DATE NOT NULL,
    study_type VARCHAR(128) NOT NULL DEFAULT 'literature',
    keywords TEXT[] NOT NULL DEFAULT '{}',
    mesh_terms TEXT[] NOT NULL DEFAULT '{}',
    reference_pmids TEXT[] NOT NULL DEFAULT '{}',
    raw_source JSONB NOT NULL,
    source_citation TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    retrieval_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pubmed_raw_pmid ON pubmed_raw_articles (pmid);
CREATE INDEX IF NOT EXISTS idx_pubmed_raw_pub_date ON pubmed_raw_articles (publication_date);
CREATE INDEX IF NOT EXISTS idx_pubmed_raw_hash ON pubmed_raw_articles (content_hash);
CREATE INDEX IF NOT EXISTS idx_pubmed_raw_journal ON pubmed_raw_articles (journal);

-- 2. Extracted Scientific Observations (16 Domain Pipelines)
CREATE TABLE IF NOT EXISTS pubmed_extracted_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    article_id UUID NOT NULL REFERENCES pubmed_raw_articles(id) ON DELETE CASCADE,
    pmid VARCHAR(64) NOT NULL,
    extraction_category VARCHAR(64) NOT NULL CHECK (
        extraction_category IN (
            'drug',
            'target',
            'gene',
            'mutation',
            'disease',
            'biomarker',
            'model',
            'cell_line',
            'animal_model',
            'efficacy',
            'toxicity',
            'cns_exposure',
            'cns_efficacy',
            'resistance',
            'combination',
            'clinical_outcome'
        )
    ),
    entity_text VARCHAR(255) NOT NULL,
    extracted_text TEXT NOT NULL,
    source_location TEXT NOT NULL,
    normalized_value NUMERIC(14, 4),
    normalized_unit VARCHAR(64),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.850 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    is_ground_truth BOOLEAN NOT NULL DEFAULT FALSE,
    epistemic_status VARCHAR(64) NOT NULL DEFAULT 'ai_inference',
    extraction_model_version VARCHAR(128) NOT NULL,
    resolved_canonical_id UUID,
    source_citation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pubmed_obs_pmid ON pubmed_extracted_observations (pmid);
CREATE INDEX IF NOT EXISTS idx_pubmed_obs_category ON pubmed_extracted_observations (extraction_category);
CREATE INDEX IF NOT EXISTS idx_pubmed_obs_entity ON pubmed_extracted_observations (entity_text);
CREATE INDEX IF NOT EXISTS idx_pubmed_obs_canonical ON pubmed_extracted_observations (resolved_canonical_id) WHERE resolved_canonical_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pubmed_obs_ground_truth ON pubmed_extracted_observations (is_ground_truth);

-- 3. Ingestion Job & Audit Log (Tracking idempotency, retries, deduplication)
CREATE TABLE IF NOT EXISTS pubmed_ingestion_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL CHECK (status IN ('INGESTED', 'DUPLICATE_SKIPPED', 'RETRIED_AND_SUCCEEDED', 'FAILED')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    content_hash VARCHAR(64) NOT NULL,
    observations_extracted INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    execution_duration_ms NUMERIC(10, 2) NOT NULL DEFAULT 0.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pubmed_audit_pmid ON pubmed_ingestion_audit_logs (pmid);
CREATE INDEX IF NOT EXISTS idx_pubmed_audit_status ON pubmed_ingestion_audit_logs (status);
