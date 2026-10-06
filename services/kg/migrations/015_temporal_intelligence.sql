-- ==============================================================================
-- Migration: 015_temporal_intelligence.sql
-- Description: Temporal Intelligence & Historical Snapshots
-- Strict multi-coordinate temporal boundary enforcement:
-- 1. Evidence publication date
-- 2. Evidence observation date
-- 3. Trial date
-- 4. Outcome date
-- 5. Regulatory date
-- 6. Prediction cutoff date
-- 7. When an outcome became publicly known
-- Prevents all information leakage in historical predictions.
-- ==============================================================================

-- 1. Outcome Availabilities (Explicit tracking of event date vs when publicly known)
CREATE TABLE IF NOT EXISTS outcome_availabilities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    outcome_type VARCHAR(64) NOT NULL CHECK (
        outcome_type IN (
            'trial_readout',
            'trial_failure',
            'regulatory_approval',
            'complete_response_letter',
            'advisory_committee_vote',
            'company_acquisition',
            'licensing_deal',
            'biomarker_discovery',
            'clinical_hold',
            'black_box_warning'
        )
    ),
    headline TEXT NOT NULL,
    description TEXT NOT NULL,
    event_date DATE NOT NULL,
    publicly_known_date DATE NOT NULL,
    disclosure_source VARCHAR(128) NOT NULL,
    disclosure_url TEXT,
    is_favorable BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_outcome_avail_asset ON outcome_availabilities (asset_id);
CREATE INDEX IF NOT EXISTS idx_outcome_avail_public_date ON outcome_availabilities (publicly_known_date);
CREATE INDEX IF NOT EXISTS idx_outcome_avail_event_date ON outcome_availabilities (event_date);

-- 2. Prediction Snapshots (Deterministic frozen model predictions at cutoff)
CREATE TABLE IF NOT EXISTS prediction_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    cutoff_date DATE NOT NULL,
    model_name VARCHAR(128) NOT NULL,
    model_version VARCHAR(32) NOT NULL DEFAULT 'v0.1',
    input_feature_hash VARCHAR(64) NOT NULL,
    predicted_action VARCHAR(32) NOT NULL CHECK (
        predicted_action IN ('PURSUE', 'INVESTIGATE', 'PARTNER', 'LICENSE', 'MONITOR', 'AVOID')
    ),
    predicted_dps INTEGER NOT NULL CHECK (predicted_dps >= 0 AND predicted_dps <= 100),
    confidence NUMERIC(4, 3) NOT NULL DEFAULT 0.900 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    rationale TEXT NOT NULL,
    eligible_evidence_count INTEGER NOT NULL DEFAULT 0,
    suppressed_future_evidence_count INTEGER NOT NULL DEFAULT 0,
    anti_leakage_audit_passed BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pred_snap_asset_cutoff ON prediction_snapshots (asset_id, cutoff_date);
CREATE INDEX IF NOT EXISTS idx_pred_snap_cutoff ON prediction_snapshots (cutoff_date);

-- 3. Historical Snapshots (Full counterfactual state evaluation)
CREATE TABLE IF NOT EXISTS historical_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prediction_snapshot_id UUID NOT NULL REFERENCES prediction_snapshots(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    cutoff_date DATE NOT NULL,
    stage_at_cutoff VARCHAR(64) NOT NULL,
    owner_at_cutoff VARCHAR(255) NOT NULL,
    primary_indication_at_cutoff VARCHAR(255) NOT NULL,
    eligible_evidence_ids UUID[] NOT NULL DEFAULT '{}',
    suppressed_future_evidence_ids UUID[] NOT NULL DEFAULT '{}',
    known_outcome_ids UUID[] NOT NULL DEFAULT '{}',
    suppressed_future_outcome_ids UUID[] NOT NULL DEFAULT '{}',
    ground_truth_outcome TEXT,
    accuracy_assessment VARCHAR(64),
    audit_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hist_snap_asset_cutoff ON historical_snapshots (asset_id, cutoff_date);
CREATE INDEX IF NOT EXISTS idx_hist_snap_cutoff ON historical_snapshots (cutoff_date);

-- 4. Temporal Audit Logs (Immutable record of anti-leakage audit passes and rejections)
CREATE TABLE IF NOT EXISTS temporal_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id UUID REFERENCES historical_snapshots(id) ON DELETE CASCADE,
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    cutoff_date DATE NOT NULL,
    audit_status VARCHAR(32) NOT NULL CHECK (audit_status IN ('PASSED', 'LEAKAGE_DETECTED', 'WARNING')),
    total_eligible_items INTEGER NOT NULL DEFAULT 0,
    total_suppressed_items INTEGER NOT NULL DEFAULT 0,
    violations_detected JSONB NOT NULL DEFAULT '[]'::jsonb,
    audit_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_temporal_audit_asset ON temporal_audit_logs (asset_id, cutoff_date);
CREATE INDEX IF NOT EXISTS idx_temporal_audit_status ON temporal_audit_logs (audit_status);
