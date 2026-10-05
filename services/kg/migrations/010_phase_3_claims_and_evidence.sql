CREATE TABLE IF NOT EXISTS canonical.claims (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE CASCADE,
    claim_type TEXT NOT NULL CHECK (claim_type IN ('source_fact', 'derived_claim', 'inference', 'prediction')),
    statement TEXT NOT NULL CHECK (length(trim(statement)) > 0),
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    confidence DOUBLE PRECISION CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    source_record_id UUID NOT NULL REFERENCES canonical.source_records(id) ON DELETE RESTRICT,
    observation_id UUID REFERENCES canonical.observations(id) ON DELETE RESTRICT,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL)),
    CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to)
);
CREATE INDEX IF NOT EXISTS claims_entity_time_idx ON canonical.claims (entity_id, valid_from, valid_to, created_at DESC);
CREATE INDEX IF NOT EXISTS claims_source_idx ON canonical.claims (source_record_id);

CREATE TABLE IF NOT EXISTS canonical.evidence_links (
    id UUID PRIMARY KEY,
    claim_id UUID NOT NULL REFERENCES canonical.claims(id) ON DELETE CASCADE,
    observation_id UUID REFERENCES canonical.observations(id) ON DELETE RESTRICT,
    source_record_id UUID REFERENCES canonical.source_records(id) ON DELETE RESTRICT,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('supporting', 'contradicting', 'context', 'derived')),
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL)),
    CHECK (observation_id IS NOT NULL OR source_record_id IS NOT NULL),
    CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to)
);
CREATE INDEX IF NOT EXISTS evidence_links_claim_idx ON canonical.evidence_links (claim_id, relation_type, created_at DESC);
CREATE INDEX IF NOT EXISTS evidence_links_observation_idx ON canonical.evidence_links (observation_id, relation_type);

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY['claims', 'evidence_links'] LOOP
        EXECUTE format('ALTER TABLE canonical.%I ENABLE ROW LEVEL SECURITY', table_name);
        EXECUTE format('ALTER TABLE canonical.%I FORCE ROW LEVEL SECURITY', table_name);
        EXECUTE format(
            'DROP POLICY IF EXISTS %I ON canonical.%I',
            table_name || '_scope', table_name
        );
        EXECUTE format(
            'CREATE POLICY %I ON canonical.%I FOR ALL USING '
            || '(organization_id IS NULL OR organization_id = canonical.current_organization_id()) '
            || 'WITH CHECK (organization_id IS NULL OR organization_id = canonical.current_organization_id())',
            table_name || '_scope', table_name
        );
    END LOOP;
END $$;
