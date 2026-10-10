-- ==============================================================================
-- Migration: 019_ownership_and_licensing_intelligence.sql
-- Description: Production Ownership, Corporate Deal & Patent Intelligence Layer
-- Tracks developer, originator, current owner, former owner, academic origin,
-- partner, licensee, licensor, acquisition, asset transfer, licensing announcement,
-- co-development, option agreement.
-- Tracks patent families, assignees, inventors, jurisdictions, priority dates,
-- expiration dates, and claim types (composition of matter, therapeutic use,
-- formulation, combination, biomarker claims).
-- Enforces:
-- 1. Never state "licensing available" unless verified.
-- 2. Strict licensing states: VERIFIED_AVAILABLE, POTENTIALLY_AVAILABLE,
--    PARTNERED, OWNERSHIP_UNCLEAR, NO_PUBLIC_LICENSING_SIGNAL, UNKNOWN.
-- 3. IP analysis is intelligence, not legal advice.
-- 4. Never claim freedom to operate (FTO).
-- ==============================================================================

-- 1. Asset Ownership Profiles
CREATE TABLE IF NOT EXISTS asset_ownership_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE UNIQUE,
    developer VARCHAR(255) NOT NULL,
    originator VARCHAR(255) NOT NULL,
    current_owner VARCHAR(255) NOT NULL,
    former_owners TEXT[] NOT NULL DEFAULT '{}',
    academic_origin VARCHAR(255),
    licensing_status VARCHAR(64) NOT NULL CHECK (
        licensing_status IN (
            'VERIFIED_AVAILABLE',
            'POTENTIALLY_AVAILABLE',
            'PARTNERED',
            'OWNERSHIP_UNCLEAR',
            'NO_PUBLIC_LICENSING_SIGNAL',
            'UNKNOWN'
        )
    ),
    licensing_status_rationale TEXT NOT NULL,
    licensing_status_verified BOOLEAN NOT NULL DEFAULT FALSE,
    licensing_verification_source TEXT,
    fto_disclaimer TEXT NOT NULL DEFAULT 'DISCLAIMER: IP analysis provided is competitive and scientific decision intelligence, not legal advice. No Freedom to Operate (FTO) is claimed or warranted. Consult qualified patent counsel for formal legal opinions.',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_asset_ownership_asset ON asset_ownership_profiles (asset_id);
CREATE INDEX IF NOT EXISTS idx_asset_ownership_status ON asset_ownership_profiles (licensing_status);
CREATE INDEX IF NOT EXISTS idx_asset_ownership_owner ON asset_ownership_profiles (current_owner);

-- 2. Ownership & Deal Events Table
CREATE TABLE IF NOT EXISTS ownership_and_deal_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    deal_type VARCHAR(64) NOT NULL CHECK (
        deal_type IN (
            'ACQUISITION',
            'ASSET_TRANSFER',
            'LICENSING_ANNOUNCEMENT',
            'CO_DEVELOPMENT',
            'OPTION_AGREEMENT'
        )
    ),
    licensor VARCHAR(255),
    licensee VARCHAR(255),
    partner VARCHAR(255),
    territory VARCHAR(128) NOT NULL DEFAULT 'Global',
    effective_date DATE NOT NULL,
    disclosed_upfront_usd BIGINT,
    disclosed_milestones_usd BIGINT,
    royalty_rate_pct VARCHAR(64),
    summary TEXT NOT NULL,
    source_citation TEXT NOT NULL,
    source_url TEXT,
    is_verified_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_deal_events_asset ON ownership_and_deal_events (asset_id, effective_date);
CREATE INDEX IF NOT EXISTS idx_deal_events_type ON ownership_and_deal_events (deal_type);

-- 3. Patent Families
CREATE TABLE IF NOT EXISTS patent_families_rich (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    family_id VARCHAR(64) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    earliest_priority_date DATE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patent_families_id ON patent_families_rich (family_id);

-- 4. Rich Patents Table
CREATE TABLE IF NOT EXISTS patents_rich (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    family_id VARCHAR(64) REFERENCES patent_families_rich(family_id) ON DELETE SET NULL,
    patent_number VARCHAR(64) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    assignee VARCHAR(255) NOT NULL,
    inventors TEXT[] NOT NULL DEFAULT '{}',
    jurisdiction VARCHAR(32) NOT NULL CHECK (
        jurisdiction IN ('US', 'EP', 'WO', 'JP', 'CN', 'CA', 'OTHER')
    ),
    filing_date DATE NOT NULL,
    priority_date DATE NOT NULL,
    expiration_date DATE NOT NULL,
    grant_date DATE,
    status VARCHAR(32) NOT NULL CHECK (
        status IN ('GRANTED', 'PENDING', 'EXPIRED', 'ABANDONED', 'REVOKED')
    ),
    claim_types VARCHAR(64)[] NOT NULL CHECK (
        claim_types <@ ARRAY[
            'COMPOSITION_OF_MATTER',
            'THERAPEUTIC_USE',
            'FORMULATION',
            'COMBINATION',
            'BIOMARKER_CLAIMS'
        ]::varchar[]
    ),
    composition_of_matter_expiry DATE,
    source_citation TEXT NOT NULL,
    source_url TEXT,
    is_verified_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patents_rich_asset ON patents_rich (asset_id);
CREATE INDEX IF NOT EXISTS idx_patents_rich_number ON patents_rich (patent_number);
CREATE INDEX IF NOT EXISTS idx_patents_rich_assignee ON patents_rich (assignee);
CREATE INDEX IF NOT EXISTS idx_patents_rich_jurisdiction ON patents_rich (jurisdiction);
CREATE INDEX IF NOT EXISTS idx_patents_rich_expiration ON patents_rich (expiration_date);
