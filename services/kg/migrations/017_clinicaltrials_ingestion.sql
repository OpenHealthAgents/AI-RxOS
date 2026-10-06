-- ==============================================================================
-- Migration: 017_clinicaltrials_ingestion.sql
-- Description: Production-Quality ClinicalTrials.gov Ingestion and Temporal Tracking
-- Normalizes 12 clinical stages, tracks status history over time, and provides
-- resolution mappings to canonical assets, indications, biomarkers, and companies.
-- ==============================================================================

-- 1. Rich Clinical Trials Table
CREATE TABLE IF NOT EXISTS clinical_trials_rich (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nct_id VARCHAR(64) NOT NULL UNIQUE,
    study_title TEXT NOT NULL,
    official_title TEXT,
    lead_sponsor VARCHAR(255) NOT NULL,
    collaborators TEXT[] NOT NULL DEFAULT '{}',
    phase_raw VARCHAR(64) NOT NULL,
    normalized_stage VARCHAR(64) NOT NULL CHECK (
        normalized_stage IN (
            'Preclinical',
            'IND-enabling',
            'Phase I',
            'Phase Ib',
            'Phase II',
            'Phase II/III',
            'Phase III',
            'Regulatory review',
            'Approved',
            'Withdrawn',
            'Terminated',
            'Discontinued'
        )
    ),
    overall_status VARCHAR(64) NOT NULL,
    enrollment INTEGER,
    interventions JSONB NOT NULL DEFAULT '[]'::jsonb,
    arms JSONB NOT NULL DEFAULT '[]'::jsonb,
    conditions TEXT[] NOT NULL DEFAULT '{}',
    biomarkers TEXT[] NOT NULL DEFAULT '{}',
    population_description TEXT,
    eligibility_criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
    endpoints JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcomes JSONB NOT NULL DEFAULT '[]'::jsonb,
    results_summary JSONB,
    adverse_events JSONB NOT NULL DEFAULT '[]'::jsonb,
    termination_reason TEXT,
    withdrawal_reason TEXT,
    publication_links TEXT[] NOT NULL DEFAULT '{}',
    start_date DATE,
    primary_completion_date DATE,
    results_first_posted_date DATE,
    content_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trials_rich_nct ON clinical_trials_rich (nct_id);
CREATE INDEX IF NOT EXISTS idx_trials_rich_stage ON clinical_trials_rich (normalized_stage);
CREATE INDEX IF NOT EXISTS idx_trials_rich_status ON clinical_trials_rich (overall_status);
CREATE INDEX IF NOT EXISTS idx_trials_rich_sponsor ON clinical_trials_rich (lead_sponsor);
CREATE INDEX IF NOT EXISTS idx_trials_rich_completion ON clinical_trials_rich (primary_completion_date);

-- 2. Status History Tracking Over Time
CREATE TABLE IF NOT EXISTS trial_status_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES clinical_trials_rich(id) ON DELETE CASCADE,
    nct_id VARCHAR(64) NOT NULL,
    as_of_date DATE NOT NULL,
    overall_status VARCHAR(64) NOT NULL,
    normalized_stage VARCHAR(64) NOT NULL,
    why_stopped TEXT,
    enrollment INTEGER,
    results_posted BOOLEAN NOT NULL DEFAULT FALSE,
    change_summary TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trial_history_nct_date ON trial_status_history (nct_id, as_of_date);
CREATE INDEX IF NOT EXISTS idx_trial_history_trial_id ON trial_status_history (trial_id);

-- 3. Trial-to-Asset Mappings
CREATE TABLE IF NOT EXISTS trial_asset_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES clinical_trials_rich(id) ON DELETE CASCADE,
    nct_id VARCHAR(64) NOT NULL,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    intervention_name VARCHAR(255) NOT NULL,
    is_primary_investigational_drug BOOLEAN NOT NULL DEFAULT TRUE,
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 1.000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (trial_id, asset_id, intervention_name)
);

CREATE INDEX IF NOT EXISTS idx_trial_asset_nct ON trial_asset_mappings (nct_id);
CREATE INDEX IF NOT EXISTS idx_trial_asset_asset_id ON trial_asset_mappings (asset_id);

-- 4. Trial-to-Indication Mappings
CREATE TABLE IF NOT EXISTS trial_indication_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES clinical_trials_rich(id) ON DELETE CASCADE,
    nct_id VARCHAR(64) NOT NULL,
    indication_id UUID REFERENCES indications(id) ON DELETE SET NULL,
    condition_name VARCHAR(255) NOT NULL,
    cancer_subtype VARCHAR(255),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.950,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trial_ind_nct ON trial_indication_mappings (nct_id);
CREATE INDEX IF NOT EXISTS idx_trial_ind_indication ON trial_indication_mappings (indication_id) WHERE indication_id IS NOT NULL;

-- 5. Trial-to-Biomarker Mappings
CREATE TABLE IF NOT EXISTS trial_biomarker_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES clinical_trials_rich(id) ON DELETE CASCADE,
    nct_id VARCHAR(64) NOT NULL,
    biomarker_id UUID REFERENCES biomarkers(id) ON DELETE SET NULL,
    biomarker_text VARCHAR(255) NOT NULL,
    gene_symbol VARCHAR(64),
    inclusion_status VARCHAR(32) NOT NULL DEFAULT 'REQUIRED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trial_bio_nct ON trial_biomarker_mappings (nct_id);
CREATE INDEX IF NOT EXISTS idx_trial_bio_gene ON trial_biomarker_mappings (gene_symbol);

-- 6. Trial-to-Company Mappings
CREATE TABLE IF NOT EXISTS trial_company_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID NOT NULL REFERENCES clinical_trials_rich(id) ON DELETE CASCADE,
    nct_id VARCHAR(64) NOT NULL,
    company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    company_name VARCHAR(255) NOT NULL,
    relationship_role VARCHAR(64) NOT NULL DEFAULT 'LEAD_SPONSOR' CHECK (
        relationship_role IN ('LEAD_SPONSOR', 'COLLABORATOR', 'FUNDER', 'STUDY_CHAIR')
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trial_comp_nct ON trial_company_mappings (nct_id);
CREATE INDEX IF NOT EXISTS idx_trial_comp_company ON trial_company_mappings (company_id) WHERE company_id IS NOT NULL;
