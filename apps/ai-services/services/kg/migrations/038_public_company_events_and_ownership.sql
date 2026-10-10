-- ==============================================================================
-- Migration: 038_public_company_events_and_ownership.sql
-- Description: Public Company Events & Temporal Ownership Resolution
-- Captures: funding, acquisition, licensing, partnership, asset transfer,
-- co-development, option.
-- Resolves ownership changes over time.
-- Licensing status support:
--   VERIFIED_AVAILABLE, POTENTIALLY_AVAILABLE, PARTNERED, OWNERSHIP_UNCLEAR,
--   NO_PUBLIC_SIGNAL, UNKNOWN.
-- ==============================================================================

-- 1. Ensure funding fields on ownership_and_deal_events
ALTER TABLE ownership_and_deal_events
    ADD COLUMN IF NOT EXISTS funding_round VARCHAR(64),
    ADD COLUMN IF NOT EXISTS investors TEXT[] DEFAULT '{}';

-- 2. Ensure partner field on asset_ownership_profiles
ALTER TABLE asset_ownership_profiles
    ADD COLUMN IF NOT EXISTS partner VARCHAR(255);

-- 3. Update Deal Type check constraint on ownership_and_deal_events
ALTER TABLE ownership_and_deal_events
    DROP CONSTRAINT IF EXISTS ownership_and_deal_events_deal_type_check;

ALTER TABLE ownership_and_deal_events
    ADD CONSTRAINT ownership_and_deal_events_deal_type_check
    CHECK (
        deal_type IN (
            'FUNDING',
            'ACQUISITION',
            'LICENSING',
            'LICENSING_ANNOUNCEMENT',
            'PARTNERSHIP',
            'ASSET_TRANSFER',
            'CO_DEVELOPMENT',
            'OPTION',
            'OPTION_AGREEMENT'
        )
    );

-- 4. Update Licensing Status check constraint on asset_ownership_profiles
ALTER TABLE asset_ownership_profiles
    DROP CONSTRAINT IF EXISTS asset_ownership_profiles_licensing_status_check;

ALTER TABLE asset_ownership_profiles
    ADD CONSTRAINT asset_ownership_profiles_licensing_status_check
    CHECK (
        licensing_status IN (
            'VERIFIED_AVAILABLE',
            'POTENTIALLY_AVAILABLE',
            'PARTNERED',
            'OWNERSHIP_UNCLEAR',
            'NO_PUBLIC_SIGNAL',
            'NO_PUBLIC_LICENSING_SIGNAL',
            'UNKNOWN'
        )
    );

-- 5. Performance indexes for deal event resolution and type queries
CREATE INDEX IF NOT EXISTS idx_deal_events_type_date ON ownership_and_deal_events (deal_type, effective_date);
CREATE INDEX IF NOT EXISTS idx_deal_events_effective_date ON ownership_and_deal_events (effective_date);
