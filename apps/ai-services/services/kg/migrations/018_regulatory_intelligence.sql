-- ==============================================================================
-- Migration: 018_regulatory_intelligence.sql
-- Description: Production Regulatory Intelligence Layer
-- Tracks IND-related, Fast Track, Breakthrough Therapy, Orphan Drug,
-- Accelerated Approval, Full Approval, Supplemental Approval, CRL,
-- Withdrawal, Safety Warning, Label Changes, and Regulatory Milestones.
-- Strictly enforces: Never infer regulatory approval from marketing claims
-- without verified evidence.
-- ==============================================================================

-- 1. Rich Regulatory Events Table
CREATE TABLE IF NOT EXISTS regulatory_events_rich (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    asset_name VARCHAR(255) NOT NULL,
    indication_id UUID REFERENCES indications(id) ON DELETE SET NULL,
    indication_name VARCHAR(255) NOT NULL,
    cancer_subtype VARCHAR(255),
    event_type VARCHAR(64) NOT NULL CHECK (
        event_type IN (
            'IND_RELATED',
            'FAST_TRACK',
            'BREAKTHROUGH_THERAPY',
            'ORPHAN_DRUG',
            'ACCELERATED_APPROVAL',
            'FULL_APPROVAL',
            'SUPPLEMENTAL_APPROVAL',
            'COMPLETE_RESPONSE_LETTER',
            'WITHDRAWAL',
            'SAFETY_WARNING',
            'LABEL_CHANGE',
            'REGULATORY_MILESTONE'
        )
    ),
    event_date DATE NOT NULL,
    jurisdiction VARCHAR(32) NOT NULL CHECK (
        jurisdiction IN ('US', 'EU', 'JP', 'CN', 'UK', 'CA', 'GLOBAL')
    ),
    authority VARCHAR(64) NOT NULL CHECK (
        authority IN ('FDA', 'EMA', 'PMDA', 'NMPA', 'MHRA', 'HEALTH_CANADA', 'WHO', 'OTHER')
    ),
    source_type VARCHAR(64) NOT NULL CHECK (
        source_type IN (
            'FDA_DRUGS_AT_FDA',
            'FDA_ACTION_LETTER',
            'FDA_ORANGE_BOOK',
            'EMA_EPAR',
            'PMDA_NOTICE',
            'NMPA_NOTICE',
            'SEC_8K_FILING',
            'FEDERAL_REGISTER',
            'SPONSOR_REGULATORY_DISCLOSURE',
            'UNVERIFIED_MARKETING_CLAIM',
            'OTHER'
        )
    ),
    source_url TEXT,
    source_citation TEXT NOT NULL,
    source_document_id VARCHAR(128),
    is_verified_evidence BOOLEAN NOT NULL DEFAULT FALSE,
    confidence NUMERIC(4, 3) NOT NULL CHECK (confidence >= 0.000 AND confidence <= 1.000),
    verification_status VARCHAR(64) NOT NULL DEFAULT 'UNVERIFIED' CHECK (
        verification_status IN (
            'VERIFIED_OFFICIAL_RECORD',
            'PROVISIONAL_PENDING_CONFIRMATION',
            'REJECTED_UNVERIFIED_MARKETING'
        )
    ),
    headline VARCHAR(255) NOT NULL,
    details TEXT NOT NULL,
    dossier_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexing for high-performance temporal queries and analytical searches
CREATE INDEX IF NOT EXISTS idx_reg_events_asset_date ON regulatory_events_rich (asset_id, event_date);
CREATE INDEX IF NOT EXISTS idx_reg_events_jurisdiction ON regulatory_events_rich (jurisdiction, authority);
CREATE INDEX IF NOT EXISTS idx_reg_events_type ON regulatory_events_rich (event_type);
CREATE INDEX IF NOT EXISTS idx_reg_events_indication ON regulatory_events_rich (indication_name);
CREATE INDEX IF NOT EXISTS idx_reg_events_verification ON regulatory_events_rich (verification_status, is_verified_evidence);

-- 2. Regulatory Audit Logs for Policy Compliance Verification
CREATE TABLE IF NOT EXISTS regulatory_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES regulatory_events_rich(id) ON DELETE CASCADE,
    action VARCHAR(64) NOT NULL,
    policy_check_passed BOOLEAN NOT NULL,
    violation_reason TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reg_audit_event ON regulatory_audit_logs (event_id);
CREATE INDEX IF NOT EXISTS idx_reg_audit_policy ON regulatory_audit_logs (policy_check_passed);
