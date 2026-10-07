-- ==============================================================================
-- Migration: 037_clinicaltrials_production_history.sql
-- Description: Production ClinicalTrials.gov Ingestion and Historical Tracking
-- Enhances clinical_trials_rich and trial_status_history with audit columns,
-- protocol amendment tracking, and index optimizations.
-- ==============================================================================

-- 1. Ensure why_stopped and termination columns on clinical_trials_rich
ALTER TABLE clinical_trials_rich
    ADD COLUMN IF NOT EXISTS why_stopped TEXT,
    ADD COLUMN IF NOT EXISTS protocol_version VARCHAR(64) DEFAULT 'v1.0',
    ADD COLUMN IF NOT EXISTS last_verified_date DATE;

-- 2. Add protocol change tracking to trial_status_history
ALTER TABLE trial_status_history
    ADD COLUMN IF NOT EXISTS amendment_number INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS previous_status VARCHAR(64),
    ADD COLUMN IF NOT EXISTS reason_for_change TEXT;

-- 3. Composite performance indexes for historical queries
CREATE INDEX IF NOT EXISTS idx_trial_history_nct_asof ON trial_status_history (nct_id, as_of_date DESC);
CREATE INDEX IF NOT EXISTS idx_trials_rich_sponsor_stage ON clinical_trials_rich (lead_sponsor, normalized_stage);
