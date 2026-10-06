-- ==============================================================================
-- Migration: 014_evidence_architecture.sql
-- Description: Rigorous Evidence Architecture for AI Drug Opportunity Discovery
-- Every scientifically meaningful statement is traceable to verified evidence.
-- Complete Lineage: Source -> Extraction -> Normalized Observation -> Derived Feature -> Model Output -> Recommendation
-- No orphaned scientific scores permitted.
-- ==============================================================================

-- 1. Evidence Sources (Publications, Trials, Regulatory, Patents, etc.)
CREATE TABLE IF NOT EXISTS evidence_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type VARCHAR(64) NOT NULL CHECK (
        source_type IN (
            'publication',
            'clinical_trial',
            'regulatory_source',
            'patent',
            'company_source',
            'conference_abstract',
            'scientific_database',
            'institutional_source'
        )
    ),
    source_id VARCHAR(255) NOT NULL,
    title TEXT NOT NULL,
    authors TEXT[] DEFAULT '{}',
    organization TEXT NOT NULL,
    publication_date DATE NOT NULL,
    retrieval_date DATE NOT NULL,
    url_reference TEXT NOT NULL,
    study_type VARCHAR(128) NOT NULL,
    phase VARCHAR(64),
    species VARCHAR(64),
    model VARCHAR(128),
    sample_size INTEGER,
    peer_reviewed BOOLEAN DEFAULT TRUE,
    prospective_or_retrospective VARCHAR(32) DEFAULT 'not_applicable' CHECK (
        prospective_or_retrospective IN ('prospective', 'retrospective', 'not_applicable')
    ),
    quality_score NUMERIC(5, 2) NOT NULL DEFAULT 85.00 CHECK (quality_score >= 0.0 AND quality_score <= 100.0),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    valid_from DATE NOT NULL,
    valid_to DATE,
    is_current BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_evidence_sources_type_id ON evidence_sources (source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_temporal ON evidence_sources (valid_from, valid_to);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_pub_date ON evidence_sources (publication_date);
CREATE INDEX IF NOT EXISTS idx_evidence_sources_quality ON evidence_sources (quality_score, confidence);

-- 2. Evidence Citations
CREATE TABLE IF NOT EXISTS evidence_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    formatted_citation TEXT NOT NULL,
    short_citation TEXT NOT NULL,
    doi VARCHAR(255),
    pmid VARCHAR(64),
    nct_id VARCHAR(64),
    patent_number VARCHAR(128),
    citation_style VARCHAR(32) NOT NULL DEFAULT 'vancouver',
    url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_citations_source_id ON evidence_citations (source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_citations_pmid ON evidence_citations (pmid) WHERE pmid IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_citations_doi ON evidence_citations (doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_citations_nct ON evidence_citations (nct_id) WHERE nct_id IS NOT NULL;

-- 3. Evidence Extractions (Exact text anchors, coordinates, extractor provenance)
CREATE TABLE IF NOT EXISTS evidence_extractions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    source_location TEXT NOT NULL,
    extracted_text TEXT NOT NULL,
    extraction_method VARCHAR(64) NOT NULL CHECK (
        extraction_method IN (
            'llm_structured_extraction',
            'regex_pipeline',
            'curated_expert',
            'ocr_table_parser'
        )
    ),
    extractor_model VARCHAR(64),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    extracted_date DATE NOT NULL,
    validation_status VARCHAR(32) NOT NULL DEFAULT 'validated' CHECK (
        validation_status IN ('validated', 'provisional', 'flagged')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_evidence_extractions_source_id ON evidence_extractions (source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_extractions_method ON evidence_extractions (extraction_method);

-- 4. Evidence Observations (Normalized scientific measurements anchored in extractions)
CREATE TABLE IF NOT EXISTS evidence_observations_rich (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    extraction_id UUID REFERENCES evidence_extractions(id) ON DELETE SET NULL,
    source_id UUID NOT NULL REFERENCES evidence_sources(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    entity VARCHAR(255) NOT NULL,
    parameter_name VARCHAR(128) NOT NULL,
    extracted_text_or_value TEXT NOT NULL,
    normalized_value NUMERIC(14, 4) NOT NULL,
    unit VARCHAR(64),
    observation_date DATE NOT NULL,
    source_location TEXT NOT NULL,
    extraction_method VARCHAR(64) NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    polarity VARCHAR(32) NOT NULL DEFAULT 'SUPPORTING' CHECK (
        polarity IN ('SUPPORTING', 'CONTRADICTORY', 'NEUTRAL')
    ),
    observation_state VARCHAR(64) NOT NULL DEFAULT 'VERIFIED_FACT' CHECK (
        observation_state IN (
            'POSITIVE',
            'NEGATIVE',
            'NEUTRAL',
            'UNKNOWN',
            'INSUFFICIENT_EVIDENCE',
            'CONFLICTING_EVIDENCE',
            'AI_INFERENCE',
            'VERIFIED_FACT'
        )
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_obs_rich_asset_id ON evidence_observations_rich (asset_id);
CREATE INDEX IF NOT EXISTS idx_obs_rich_source_id ON evidence_observations_rich (source_id);
CREATE INDEX IF NOT EXISTS idx_obs_rich_extraction_id ON evidence_observations_rich (extraction_id);
CREATE INDEX IF NOT EXISTS idx_obs_rich_param_date ON evidence_observations_rich (parameter_name, observation_date);
CREATE INDEX IF NOT EXISTS idx_obs_rich_temporal_as_of ON evidence_observations_rich (asset_id, observation_date);

-- 5. Evidence Claims (High-level syntheses with supporting and conflicting observations)
CREATE TABLE IF NOT EXISTS evidence_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    claim_type VARCHAR(64) NOT NULL CHECK (
        claim_type IN (
            'efficacy',
            'selectivity',
            'safety_tolerability',
            'cns_penetration',
            'resistance_risk',
            'commercial_fto'
        )
    ),
    polarity VARCHAR(32) NOT NULL DEFAULT 'SUPPORTING' CHECK (
        polarity IN ('SUPPORTING', 'CONTRADICTORY', 'NEUTRAL')
    ),
    epistemic_status VARCHAR(64) NOT NULL DEFAULT 'VERIFIED_FACT' CHECK (
        epistemic_status IN (
            'POSITIVE',
            'NEGATIVE',
            'NEUTRAL',
            'UNKNOWN',
            'INSUFFICIENT_EVIDENCE',
            'CONFLICTING_EVIDENCE',
            'AI_INFERENCE',
            'VERIFIED_FACT'
        )
    ),
    synthesis_confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (synthesis_confidence >= 0.0 AND synthesis_confidence <= 1.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claims_asset_id ON evidence_claims (asset_id);
CREATE INDEX IF NOT EXISTS idx_claims_type ON evidence_claims (claim_type);

-- 6. Claim-Observation Links
CREATE TABLE IF NOT EXISTS evidence_claim_observations (
    claim_id UUID NOT NULL REFERENCES evidence_claims(id) ON DELETE CASCADE,
    observation_id UUID NOT NULL REFERENCES evidence_observations_rich(id) ON DELETE CASCADE,
    relationship_role VARCHAR(32) NOT NULL DEFAULT 'supports' CHECK (
        relationship_role IN ('supports', 'contradicts', 'contextualizes')
    ),
    PRIMARY KEY (claim_id, observation_id)
);

CREATE INDEX IF NOT EXISTS idx_claim_obs_obs_id ON evidence_claim_observations (observation_id);

-- 7. Derived Features (Intermediary normalized quantitative inputs for models)
CREATE TABLE IF NOT EXISTS derived_features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    feature_name VARCHAR(128) NOT NULL,
    computed_value NUMERIC(10, 4) NOT NULL,
    calculation_formula TEXT NOT NULL,
    formula_version VARCHAR(32) NOT NULL DEFAULT 'v1.0',
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_derived_features_asset_feature ON derived_features (asset_id, feature_name);

-- 8. Derived Feature -> Observation Provenance Links
CREATE TABLE IF NOT EXISTS derived_feature_observations (
    feature_id UUID NOT NULL REFERENCES derived_features(id) ON DELETE CASCADE,
    observation_id UUID NOT NULL REFERENCES evidence_observations_rich(id) ON DELETE CASCADE,
    weight NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    PRIMARY KEY (feature_id, observation_id)
);

CREATE INDEX IF NOT EXISTS idx_feature_obs_obs_id ON derived_feature_observations (observation_id);

-- 9. Model Outputs (Scores, transition probabilities, predicted outcomes)
CREATE TABLE IF NOT EXISTS model_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(32) NOT NULL DEFAULT 'v0.1',
    output_metric VARCHAR(128) NOT NULL,
    output_value NUMERIC(10, 4) NOT NULL,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_outputs_asset ON model_outputs (asset_id, model_name, output_metric);

-- 10. Model Output -> Derived Feature Lineage Links
CREATE TABLE IF NOT EXISTS model_output_features (
    model_output_id UUID NOT NULL REFERENCES model_outputs(id) ON DELETE CASCADE,
    feature_id UUID NOT NULL REFERENCES derived_features(id) ON DELETE CASCADE,
    weight NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    PRIMARY KEY (model_output_id, feature_id)
);

-- 11. Recommendation Lineage Links (Connecting final recommendations directly to model outputs)
CREATE TABLE IF NOT EXISTS recommendation_lineages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recommendation_id UUID NOT NULL REFERENCES recommendations(id) ON DELETE CASCADE,
    model_output_id UUID NOT NULL REFERENCES model_outputs(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    lineage_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rec_lineage_rec_id ON recommendation_lineages (recommendation_id);
CREATE INDEX IF NOT EXISTS idx_rec_lineage_asset ON recommendation_lineages (asset_id);

-- 12. General Evidence Relationships (Graph representation for fast DAG traversals)
CREATE TABLE IF NOT EXISTS evidence_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_entity_id UUID NOT NULL,
    source_entity_type VARCHAR(64) NOT NULL,
    target_entity_id UUID NOT NULL,
    target_entity_type VARCHAR(64) NOT NULL,
    relationship_type VARCHAR(64) NOT NULL CHECK (
        relationship_type IN (
            'supports',
            'contradicts',
            'derives_into',
            'calibrates',
            'contextualizes',
            'rebuts'
        )
    ),
    lineage_step VARCHAR(64) NOT NULL CHECK (
        lineage_step IN (
            'source_to_extraction',
            'extraction_to_observation',
            'observation_to_claim',
            'observation_to_feature',
            'feature_to_model_output',
            'model_output_to_recommendation'
        )
    ),
    weight NUMERIC(5, 4) NOT NULL DEFAULT 1.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ev_rel_source ON evidence_relationships (source_entity_id, source_entity_type);
CREATE INDEX IF NOT EXISTS idx_ev_rel_target ON evidence_relationships (target_entity_id, target_entity_type);
CREATE INDEX IF NOT EXISTS idx_ev_rel_step ON evidence_relationships (lineage_step);
