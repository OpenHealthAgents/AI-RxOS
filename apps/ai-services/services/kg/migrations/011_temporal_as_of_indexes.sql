CREATE INDEX IF NOT EXISTS claims_entity_availability_idx
    ON canonical.claims (entity_id, created_at DESC);

CREATE INDEX IF NOT EXISTS evidence_links_claim_availability_idx
    ON canonical.evidence_links (claim_id, created_at DESC);