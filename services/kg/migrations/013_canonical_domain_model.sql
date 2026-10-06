-- Migration 013: Canonical Biomedical Domain Model for Drug Opportunity Intelligence
-- Defines complete relational architecture for assets, targets, biology, clinical, safety, IP, and decisions.

CREATE SCHEMA IF NOT EXISTS canonical;

-- 1. Organizations & Users
CREATE TABLE IF NOT EXISTS canonical.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'enterprise' CHECK (tier IN ('starter', 'team', 'enterprise')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID REFERENCES canonical.organizations(id) ON DELETE SET NULL,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'researcher' CHECK (role IN ('admin', 'oncologist', 'bd_lead', 'researcher', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. Companies, Institutions, Sponsors
CREATE TABLE IF NOT EXISTS canonical.companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    ticker TEXT,
    country TEXT,
    headquarters TEXT,
    company_type TEXT CHECK (company_type IN ('pharma', 'biotech', 'academic', 'cro', 'other')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_normalized_name ON canonical.companies(normalized_name);

CREATE TABLE IF NOT EXISTS canonical.institutions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    institution_type TEXT CHECK (institution_type IN ('university', 'cancer_center', 'hospital', 'research_institute')),
    city TEXT,
    country TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_institutions_normalized_name ON canonical.institutions(normalized_name);

CREATE TABLE IF NOT EXISTS canonical.sponsors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    company_id UUID REFERENCES canonical.companies(id) ON DELETE SET NULL,
    institution_id UUID REFERENCES canonical.institutions(id) ON DELETE SET NULL,
    sponsor_type TEXT NOT NULL CHECK (sponsor_type IN ('industry', 'nih', 'academic', 'other')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 3. Targets, Genes, Proteins
CREATE TABLE IF NOT EXISTS canonical.genes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hgnc_symbol TEXT NOT NULL UNIQUE,
    hgnc_id TEXT,
    entrez_id TEXT,
    ensembl_id TEXT,
    full_name TEXT NOT NULL,
    chromosome TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.proteins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    uniprot_id TEXT NOT NULL UNIQUE,
    gene_id UUID REFERENCES canonical.genes(id) ON DELETE SET NULL,
    protein_name TEXT NOT NULL,
    sequence_length INT,
    molecular_weight DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    gene_id UUID REFERENCES canonical.genes(id) ON DELETE SET NULL,
    protein_id UUID REFERENCES canonical.proteins(id) ON DELETE SET NULL,
    target_class TEXT NOT NULL CHECK (target_class IN ('kinase', 'gpcr', 'ion_channel', 'nuclear_receptor', 'enzyme', 'surface_antigen', 'other')),
    validation_level TEXT CHECK (validation_level IN ('clinically_validated', 'preclinically_validated', 'exploratory')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_targets_symbol ON canonical.targets(symbol);

-- 4. Diseases, Indications, Cancer Subtypes
CREATE TABLE IF NOT EXISTS canonical.diseases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    mesh_id TEXT,
    icd10_code TEXT,
    doid TEXT,
    category TEXT NOT NULL CHECK (category IN ('oncology', 'immunology', 'neurology', 'cardiovascular', 'rare_disease', 'other')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_diseases_name ON canonical.diseases(name);

CREATE TABLE IF NOT EXISTS canonical.indications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disease_id UUID REFERENCES canonical.diseases(id) ON DELETE RESTRICT,
    name TEXT NOT NULL,
    setting TEXT CHECK (setting IN ('first_line', 'second_line', 'relapsed_refractory', 'adjuvant', 'extended_adjuvant', 'neoadjuvant', 'maintenance')),
    line_of_therapy INT,
    prevalence_annual INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.cancer_subtypes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    disease_id UUID REFERENCES canonical.diseases(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    receptor_status TEXT, -- e.g., 'ER+/HER2-', 'Triple-Negative'
    histology TEXT,
    frequency_percentage DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 5. Biomarkers & Mutations
CREATE TABLE IF NOT EXISTS canonical.biomarkers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    target_id UUID REFERENCES canonical.targets(id) ON DELETE SET NULL,
    biomarker_type TEXT NOT NULL CHECK (biomarker_type IN ('mutation', 'amplification', 'fusion', 'expression', 'msi', 'tmb', 'loss')),
    diagnostic_test_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.mutations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    biomarker_id UUID REFERENCES canonical.biomarkers(id) ON DELETE CASCADE,
    gene_id UUID REFERENCES canonical.genes(id) ON DELETE SET NULL,
    protein_change TEXT NOT NULL, -- e.g., 'L755S', 'V777L', 'Exon 20 insertion'
    exon INT,
    functional_consequence TEXT CHECK (functional_consequence IN ('activating', 'resistance_gatekeeper', 'loss_of_function', 'unknown')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 6. Modality & Mechanism of Action
CREATE TABLE IF NOT EXISTS canonical.modalities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE CHECK (code IN (
        'SMALL_MOLECULE', 'ANTIBODY', 'ADC', 'PROTEIN', 'PEPTIDE',
        'CELL_THERAPY', 'GENE_THERAPY', 'RNA_THERAPY', 'RADIOPHARMACEUTICAL', 'VACCINE', 'OTHER'
    )),
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.mechanisms_of_action (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id UUID REFERENCES canonical.targets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    binding_type TEXT CHECK (binding_type IN ('irreversible_covalent', 'reversible_competitive', 'allosteric', 'degrader_protac', 'antagonist', 'agonist')),
    selectivity_profile TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 7. Core Asset Entity
CREATE TABLE IF NOT EXISTS canonical.assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    preferred_name TEXT NOT NULL,
    canonical_slug TEXT NOT NULL UNIQUE,
    modality_id UUID REFERENCES canonical.modalities(id) ON DELETE RESTRICT,
    primary_target_id UUID REFERENCES canonical.targets(id) ON DELETE SET NULL,
    primary_moa_id UUID REFERENCES canonical.mechanisms_of_action(id) ON DELETE SET NULL,
    owner_company_id UUID REFERENCES canonical.companies(id) ON DELETE SET NULL,
    developer_company_id UUID REFERENCES canonical.companies(id) ON DELETE SET NULL,
    sponsor_id UUID REFERENCES canonical.sponsors(id) ON DELETE SET NULL,
    current_development_stage TEXT NOT NULL CHECK (current_development_stage IN ('Preclinical', 'Phase I', 'Phase II', 'Phase III', 'Approved', 'Terminated')),
    status_label TEXT NOT NULL DEFAULT 'Investigational' CHECK (status_label IN ('Investigational', 'Approved', 'Preclinical', 'Terminated')),
    primary_indication_id UUID REFERENCES canonical.indications(id) ON DELETE SET NULL,
    is_deprecated BOOLEAN NOT NULL DEFAULT FALSE,
    merged_into_asset_id UUID REFERENCES canonical.assets(id) ON DELETE SET NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assets_stage ON canonical.assets(current_development_stage);
CREATE INDEX IF NOT EXISTS idx_assets_target ON canonical.assets(primary_target_id);

-- 8. Asset Identifiers, Development Codes, Aliases
CREATE TABLE IF NOT EXISTS canonical.asset_development_codes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    code TEXT NOT NULL,
    normalized_code TEXT NOT NULL,
    originator_company_id UUID REFERENCES canonical.companies(id) ON DELETE SET NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_dev_codes_normalized ON canonical.asset_development_codes(normalized_code);
CREATE INDEX IF NOT EXISTS idx_dev_codes_asset_id ON canonical.asset_development_codes(asset_id);

CREATE TABLE IF NOT EXISTS canonical.asset_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    alias_type TEXT NOT NULL CHECK (alias_type IN ('generic_name', 'brand_name', 'former_name', 'chemical_name', 'laboratory_code', 'synonym')),
    is_primary_for_type BOOLEAN NOT NULL DEFAULT FALSE,
    verification_state TEXT NOT NULL DEFAULT 'verified' CHECK (verification_state IN ('unreviewed', 'verified', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_asset_aliases_normalized ON canonical.asset_aliases(normalized_alias, alias_type);
CREATE INDEX IF NOT EXISTS idx_asset_aliases_asset ON canonical.asset_aliases(asset_id);

-- 9. Trials, Studies, Publications
CREATE TABLE IF NOT EXISTS canonical.trials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nct_id TEXT NOT NULL UNIQUE,
    brief_title TEXT NOT NULL,
    official_title TEXT,
    phase TEXT NOT NULL CHECK (phase IN ('Early Phase 1', 'Phase 1', 'Phase 1/Phase 2', 'Phase 2', 'Phase 2/Phase 3', 'Phase 3', 'Phase 4', 'Not Applicable')),
    overall_status TEXT NOT NULL,
    sponsor_id UUID REFERENCES canonical.sponsors(id) ON DELETE SET NULL,
    enrollment INT,
    primary_completion_date DATE,
    results_first_posted DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID REFERENCES canonical.trials(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    study_type TEXT NOT NULL CHECK (study_type IN ('interventional_trial', 'observational_cohort', 'in_vitro_assay', 'in_vivo_xenograft', 'pdx_model', 'pk_pd_study')),
    lead_institution_id UUID REFERENCES canonical.institutions(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.publications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid TEXT UNIQUE,
    doi TEXT UNIQUE,
    pmcid TEXT,
    title TEXT NOT NULL,
    journal TEXT,
    publication_year INT NOT NULL,
    published_date DATE,
    url TEXT,
    authors JSONB DEFAULT '[]'::jsonb,
    abstract TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_publications_year ON canonical.publications(publication_year);

-- 10. Evidence & Evidence Observations
CREATE TABLE IF NOT EXISTS canonical.evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    publication_id UUID REFERENCES canonical.publications(id) ON DELETE SET NULL,
    trial_id UUID REFERENCES canonical.trials(id) ON DELETE SET NULL,
    evidence_type TEXT NOT NULL CHECK (evidence_type IN ('literature', 'clinical_trial', 'fda_label', 'regulatory_authority', 'patent', 'conference_abstract')),
    source_ref TEXT NOT NULL,
    citation TEXT NOT NULL,
    publication_year INT NOT NULL,
    as_of_date DATE NOT NULL,
    polarity TEXT NOT NULL CHECK (polarity IN ('SUPPORTING', 'CONTRADICTING', 'NEUTRAL')),
    is_verified BOOLEAN NOT NULL DEFAULT TRUE,
    excerpt TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evidence_asset_polarity ON canonical.evidence(asset_id, polarity);
CREATE INDEX IF NOT EXISTS idx_evidence_as_of_date ON canonical.evidence(as_of_date);

CREATE TABLE IF NOT EXISTS canonical.evidence_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID NOT NULL REFERENCES canonical.evidence(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    parameter_name TEXT NOT NULL, -- e.g. 'IC50', 'ORR', 'PFS', 'Diarrhea_Rate'
    observed_value TEXT NOT NULL,
    numeric_value DOUBLE PRECISION,
    unit TEXT,
    statistical_significance TEXT, -- e.g. 'p < 0.001', '95% CI: 0.45-0.78'
    observation_state TEXT NOT NULL DEFAULT 'verified_fact' CHECK (observation_state IN (
        'positive', 'negative', 'neutral', 'unknown',
        'insufficient_evidence', 'conflicting_evidence', 'ai_inference', 'verified_fact'
    )),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 11. Clinical Outcomes & Preclinical Results
CREATE TABLE IF NOT EXISTS canonical.clinical_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id UUID REFERENCES canonical.trials(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    endpoint_name TEXT NOT NULL, -- 'ORR', 'mPFS', 'mOS', 'DCR'
    endpoint_type TEXT NOT NULL CHECK (endpoint_type IN ('primary', 'secondary', 'exploratory')),
    cohort_description TEXT,
    response_rate DOUBLE PRECISION,
    median_months DOUBLE PRECISION,
    hazard_ratio DOUBLE PRECISION,
    confidence_interval TEXT,
    is_statistically_significant BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.preclinical_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    assay_type TEXT NOT NULL CHECK (assay_type IN ('biochemical_kinase', 'cell_proliferation', 'cdx_xenograft', 'pdx_model', 'pharmacokinetics')),
    target_id UUID REFERENCES canonical.targets(id) ON DELETE SET NULL,
    cell_line TEXT,
    ic50_nm DOUBLE PRECISION,
    ec50_nm DOUBLE PRECISION,
    tumor_growth_inhibition_pct DOUBLE PRECISION,
    is_wt_sparing BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 12. Safety & CNS Observations
CREATE TABLE IF NOT EXISTS canonical.safety_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    adverse_event_name TEXT NOT NULL, -- e.g., 'Diarrhea', 'Rash', 'ILD', 'Cardiotoxicity'
    grade_all_rate DOUBLE PRECISION,
    grade_3_plus_rate DOUBLE PRECISION,
    dose_limiting_toxicity BOOLEAN NOT NULL DEFAULT FALSE,
    discontinuation_rate DOUBLE PRECISION,
    therapeutic_index_rating TEXT CHECK (therapeutic_index_rating IN ('narrow', 'moderate', 'favorable', 'wide')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.cns_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    brain_to_plasma_ratio DOUBLE PRECISION,
    csf_penetration_verified BOOLEAN NOT NULL DEFAULT FALSE,
    intracranial_orr DOUBLE PRECISION,
    intracranial_pfs_months DOUBLE PRECISION,
    leptomeningeal_activity BOOLEAN NOT NULL DEFAULT FALSE,
    cns_score INT CHECK (cns_score BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 13. Patient Populations, Resistance & Combinations
CREATE TABLE IF NOT EXISTS canonical.patient_populations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    population_name TEXT NOT NULL,
    indication_id UUID REFERENCES canonical.indications(id) ON DELETE SET NULL,
    biomarker_id UUID REFERENCES canonical.biomarkers(id) ON DELETE SET NULL,
    prior_lines TEXT,
    cns_metastases_benefit BOOLEAN DEFAULT TRUE,
    match_score DOUBLE PRECISION CHECK (match_score BETWEEN 0 AND 100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.resistance_mechanisms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    impact_level TEXT NOT NULL CHECK (impact_level IN ('High', 'Moderate', 'Low')),
    is_predicted BOOLEAN NOT NULL DEFAULT FALSE,
    mechanism_description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.combinations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    primary_asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    partner_name TEXT NOT NULL,
    partner_asset_id UUID REFERENCES canonical.assets(id) ON DELETE SET NULL,
    synergy_type TEXT NOT NULL,
    rationale TEXT NOT NULL,
    clinical_status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 14. Patents, License Events, Partnerships, Regulatory Events
CREATE TABLE IF NOT EXISTS canonical.patents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patent_number TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    assignee_company_id UUID REFERENCES canonical.companies(id) ON DELETE SET NULL,
    priority_date DATE,
    filing_date DATE,
    grant_date DATE,
    expiration_date DATE,
    status TEXT NOT NULL CHECK (status IN ('granted', 'pending', 'expired', 'abandoned')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.license_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    licensor_company_id UUID REFERENCES canonical.companies(id) ON DELETE RESTRICT,
    licensee_company_id UUID REFERENCES canonical.companies(id) ON DELETE RESTRICT,
    event_type TEXT NOT NULL CHECK (event_type IN ('exclusive_license', 'non_exclusive_license', 'option_agreement', 'co_development', 'divestment')),
    territory TEXT NOT NULL DEFAULT 'Global',
    effective_date DATE NOT NULL,
    disclosed_upfront_usd BIGINT,
    disclosed_milestones_usd BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.partnerships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    partner_company_id UUID NOT NULL REFERENCES canonical.companies(id) ON DELETE RESTRICT,
    scope TEXT NOT NULL,
    start_date DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'terminated', 'completed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.regulatory_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    authority TEXT NOT NULL CHECK (authority IN ('FDA', 'EMA', 'PMDA', 'NMPA', 'MHRA', 'Health_Canada')),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'IND_cleared', 'orphan_designation', 'fast_track', 'breakthrough_therapy',
        'priority_review', 'NDA_BLA_accepted', 'approval', 'complete_response_letter', 'clinical_hold'
    )),
    indication_id UUID REFERENCES canonical.indications(id) ON DELETE SET NULL,
    event_date DATE NOT NULL,
    dossier_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_regulatory_asset_date ON canonical.regulatory_events(asset_id, event_date);

-- 15. Commercial Observations & Competitive Assets
CREATE TABLE IF NOT EXISTS canonical.commercial_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    estimated_peak_sales_usd BIGINT,
    addressable_market_usd BIGINT,
    target_patient_annual_count INT,
    pricing_strategy TEXT,
    market_exclusivity_expiry DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.competitive_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    competitor_asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    competitive_relationship TEXT NOT NULL CHECK (competitive_relationship IN ('direct_benchmark', 'class_competitor', 'preceding_standard_of_care', 'novel_challenger')),
    differentiating_advantage TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_competitive_pair UNIQUE (target_asset_id, competitor_asset_id)
);

-- 16. Decision Intelligence: Decisions, Recommendations, Scores, Predictions
CREATE TABLE IF NOT EXISTS canonical.decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    organization_id UUID REFERENCES canonical.organizations(id) ON DELETE SET NULL,
    user_id UUID REFERENCES canonical.users(id) ON DELETE SET NULL,
    action TEXT NOT NULL CHECK (action IN ('PURSUE', 'INVESTIGATE', 'PARTNER', 'LICENSE', 'MONITOR', 'AVOID')),
    is_human_override BOOLEAN NOT NULL DEFAULT FALSE,
    ai_suggested_action TEXT NOT NULL CHECK (ai_suggested_action IN ('PURSUE', 'INVESTIGATE', 'PARTNER', 'LICENSE', 'MONITOR', 'AVOID')),
    clinical_justification TEXT NOT NULL,
    decision_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checklist JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS canonical.recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('PURSUE', 'INVESTIGATE', 'PARTNER', 'LICENSE', 'MONITOR', 'AVOID')),
    confidence DOUBLE PRECISION NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    rationale TEXT NOT NULL,
    badge_text TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT 'Model v0.1',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    score_type TEXT NOT NULL CHECK (score_type IN ('development_potential', 'target_selectivity', 'cns_potential', 'safety_index', 'patient_match')),
    numeric_score DOUBLE PRECISION NOT NULL CHECK (numeric_score BETWEEN 0 AND 100),
    confidence_interval_low DOUBLE PRECISION,
    confidence_interval_high DOUBLE PRECISION,
    model_lineage TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.score_components (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    score_id UUID NOT NULL REFERENCES canonical.scores(id) ON DELETE CASCADE,
    component_name TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL,
    raw_value DOUBLE PRECISION NOT NULL,
    weighted_value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.predictions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    transition_stage TEXT NOT NULL CHECK (transition_stage IN ('preclinical_to_ind', 'phase_i_to_ii', 'phase_ii_to_iii', 'phase_iii_to_approval')),
    predicted_probability DOUBLE PRECISION NOT NULL CHECK (predicted_probability BETWEEN 0 AND 1),
    model_version TEXT NOT NULL,
    calibration_data TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 17. Backtest Snapshots
CREATE TABLE IF NOT EXISTS canonical.backtest_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    cutoff_date DATE NOT NULL,
    predicted_action TEXT NOT NULL CHECK (predicted_action IN ('PURSUE', 'INVESTIGATE', 'PARTNER', 'LICENSE', 'MONITOR', 'AVOID')),
    predicted_dps DOUBLE PRECISION NOT NULL,
    eligible_evidence_count INT NOT NULL,
    suppressed_future_evidence_count INT NOT NULL,
    ground_truth_outcome TEXT NOT NULL,
    prediction_accuracy TEXT NOT NULL CHECK (prediction_accuracy IN ('True Positive', 'True Negative', 'Calibrated Success', 'Consistent Divergence')),
    anti_leakage_audit_passed BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_backtest_asset_cutoff ON canonical.backtest_snapshots(asset_id, cutoff_date);

-- 18. Audit Events & Provenance
CREATE TABLE IF NOT EXISTS canonical.audit_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'ASSET_CREATED', 'ALIAS_ATTACHED', 'DEV_CODE_ATTACHED', 'ASSET_MERGED',
        'DECISION_RATIFIED', 'DECISION_OVERRIDDEN', 'EVIDENCE_INGESTED', 'SCORE_RECALCULATED'
    )),
    entity_id UUID NOT NULL,
    entity_type TEXT NOT NULL,
    actor_id UUID REFERENCES canonical.users(id) ON DELETE SET NULL,
    actor_name TEXT NOT NULL,
    summary TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON canonical.audit_events(entity_id, created_at DESC);

-- 19. Many-to-Many Asset Association Tables
CREATE TABLE IF NOT EXISTS canonical.asset_targets (
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    target_id UUID NOT NULL REFERENCES canonical.targets(id) ON DELETE CASCADE,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (asset_id, target_id)
);

CREATE TABLE IF NOT EXISTS canonical.asset_indications (
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    indication_id UUID NOT NULL REFERENCES canonical.indications(id) ON DELETE CASCADE,
    is_lead BOOLEAN NOT NULL DEFAULT FALSE,
    stage TEXT,
    PRIMARY KEY (asset_id, indication_id)
);

CREATE TABLE IF NOT EXISTS canonical.asset_trials (
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    trial_id UUID NOT NULL REFERENCES canonical.trials(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, trial_id)
);

CREATE TABLE IF NOT EXISTS canonical.asset_publications (
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    publication_id UUID NOT NULL REFERENCES canonical.publications(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, publication_id)
);

CREATE TABLE IF NOT EXISTS canonical.asset_patents (
    asset_id UUID NOT NULL REFERENCES canonical.assets(id) ON DELETE CASCADE,
    patent_id UUID NOT NULL REFERENCES canonical.patents(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, patent_id)
);
