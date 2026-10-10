-- ==============================================================================
-- Migration: 034_evidence_temporal_metadata.sql
-- Description: Temporal Metadata & Multi-Coordinate Time Querying Schema
-- Tracks all 8 distinct temporal coordinates for all evidence:
-- 1. publication date
-- 2. observation date
-- 3. trial date
-- 4. outcome date
-- 5. regulatory date
-- 6. licensing date
-- 7. prediction cutoff
-- 8. public availability date
-- All evidence is queryable by time.
-- ==============================================================================

-- 1. Extend evidence_sources with all temporal coordinates
ALTER TABLE evidence_sources
    ADD COLUMN IF NOT EXISTS observation_date DATE,
    ADD COLUMN IF NOT EXISTS trial_date DATE,
    ADD COLUMN IF NOT EXISTS outcome_date DATE,
    ADD COLUMN IF NOT EXISTS regulatory_date DATE,
    ADD COLUMN IF NOT EXISTS licensing_date DATE,
    ADD COLUMN IF NOT EXISTS prediction_cutoff DATE,
    ADD COLUMN IF NOT EXISTS public_availability_date DATE;

-- Populate public_availability_date from publication_date where null
UPDATE evidence_sources
SET public_availability_date = publication_date
WHERE public_availability_date IS NULL AND publication_date IS NOT NULL;

-- 2. Extend evidence_observations_rich with full temporal coordinates
ALTER TABLE evidence_observations_rich
    ADD COLUMN IF NOT EXISTS publication_date DATE,
    ADD COLUMN IF NOT EXISTS trial_date DATE,
    ADD COLUMN IF NOT EXISTS outcome_date DATE,
    ADD COLUMN IF NOT EXISTS regulatory_date DATE,
    ADD COLUMN IF NOT EXISTS licensing_date DATE,
    ADD COLUMN IF NOT EXISTS prediction_cutoff DATE,
    ADD COLUMN IF NOT EXISTS public_availability_date DATE;

-- Populate public_availability_date from observation_date where null
UPDATE evidence_observations_rich
SET public_availability_date = observation_date
WHERE public_availability_date IS NULL AND observation_date IS NOT NULL;

-- 3. High-performance B-Tree indexes for temporal slicing and range queries
CREATE INDEX IF NOT EXISTS idx_evidence_sources_obs_date ON evidence_sources (observation_date) WHERE observation_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_sources_trial_date ON evidence_sources (trial_date) WHERE trial_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_sources_outcome_date ON evidence_sources (outcome_date) WHERE outcome_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_sources_reg_date ON evidence_sources (regulatory_date) WHERE regulatory_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_sources_lic_date ON evidence_sources (licensing_date) WHERE licensing_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_sources_cutoff ON evidence_sources (prediction_cutoff) WHERE prediction_cutoff IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_sources_public_avail ON evidence_sources (public_availability_date) WHERE public_availability_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_evidence_obs_pub_date ON evidence_observations_rich (publication_date) WHERE publication_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_obs_trial_date ON evidence_observations_rich (trial_date) WHERE trial_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_obs_reg_date ON evidence_observations_rich (regulatory_date) WHERE regulatory_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_obs_lic_date ON evidence_observations_rich (licensing_date) WHERE licensing_date IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_obs_cutoff ON evidence_observations_rich (prediction_cutoff) WHERE prediction_cutoff IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_evidence_obs_public_avail ON evidence_observations_rich (public_availability_date) WHERE public_availability_date IS NOT NULL;

-- 4. Unified Temporal Query View
CREATE OR REPLACE VIEW view_evidence_temporal_coordinates AS
SELECT
    s.id AS source_id,
    o.id AS observation_id,
    o.asset_id,
    s.source_type,
    s.source_id AS external_source_id,
    s.title,
    o.parameter_name,
    o.normalized_value,
    o.unit,
    COALESCE(s.publication_date, o.publication_date) AS publication_date,
    COALESCE(o.observation_date, s.observation_date) AS observation_date,
    COALESCE(s.trial_date, o.trial_date) AS trial_date,
    COALESCE(s.outcome_date, o.outcome_date) AS outcome_date,
    COALESCE(s.regulatory_date, o.regulatory_date) AS regulatory_date,
    COALESCE(s.licensing_date, o.licensing_date) AS licensing_date,
    COALESCE(s.prediction_cutoff, o.prediction_cutoff) AS prediction_cutoff,
    COALESCE(s.public_availability_date, o.public_availability_date, s.publication_date, o.observation_date) AS public_availability_date
FROM evidence_sources s
LEFT JOIN evidence_observations_rich o ON s.id = o.source_id;
