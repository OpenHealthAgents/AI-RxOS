-- ==============================================================================
-- Migration: 035_historical_snapshots_cutoff_fields.sql
-- Description: Historical Snapshots Cutoff Coordinates & Anti-Leakage Tracking
-- Explicitly supports:
-- 1. prediction_cutoff: Point-in-time boundary for historical prediction/decision
-- 2. evidence_cutoff: Point-in-time boundary for admissible scientific evidence
-- 3. outcome_known_at_cutoff: Explicit flag whether target outcome was publicly known
-- ==============================================================================

-- 1. Add prediction_cutoff, evidence_cutoff, outcome_known_at_cutoff columns to historical_snapshots
ALTER TABLE historical_snapshots
    ADD COLUMN IF NOT EXISTS prediction_cutoff DATE,
    ADD COLUMN IF NOT EXISTS evidence_cutoff DATE,
    ADD COLUMN IF NOT EXISTS outcome_known_at_cutoff BOOLEAN NOT NULL DEFAULT FALSE;

-- 2. Backfill existing records
UPDATE historical_snapshots
SET prediction_cutoff = cutoff_date,
    evidence_cutoff = cutoff_date
WHERE prediction_cutoff IS NULL;

-- 3. Set NOT NULL constraint once backfilled
ALTER TABLE historical_snapshots
    ALTER COLUMN prediction_cutoff SET NOT NULL,
    ALTER COLUMN evidence_cutoff SET NOT NULL;

-- 4. Check constraint ensuring evidence_cutoff <= prediction_cutoff (prevents future information leakage)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_hist_snap_no_future_evidence_leakage'
    ) THEN
        ALTER TABLE historical_snapshots
            ADD CONSTRAINT chk_hist_snap_no_future_evidence_leakage
            CHECK (evidence_cutoff <= prediction_cutoff);
    END IF;
END $$;

-- 5. Indexes for fast range queries and historical evaluation searches
CREATE INDEX IF NOT EXISTS idx_hist_snap_pred_cutoff ON historical_snapshots (prediction_cutoff);
CREATE INDEX IF NOT EXISTS idx_hist_snap_ev_cutoff ON historical_snapshots (evidence_cutoff);
CREATE INDEX IF NOT EXISTS idx_hist_snap_asset_pred ON historical_snapshots (asset_id, prediction_cutoff);
CREATE INDEX IF NOT EXISTS idx_hist_snap_outcome_known ON historical_snapshots (outcome_known_at_cutoff);
