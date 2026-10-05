CREATE SCHEMA IF NOT EXISTS canonical;

CREATE OR REPLACE FUNCTION canonical.current_organization_id() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.canonical_organization_id', true), '')::uuid
$$;

CREATE TABLE IF NOT EXISTS canonical.schema_migrations (
    migration_id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS canonical.source_records (
    id UUID PRIMARY KEY,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    namespace TEXT NOT NULL CHECK (length(trim(namespace)) > 0),
    external_id TEXT NOT NULL CHECK (length(trim(external_id)) > 0),
    source_type TEXT NOT NULL CHECK (source_type IN (
        'publication', 'trial_registry', 'patent_registry', 'regulatory_authority',
        'company', 'database', 'manual', 'demo'
    )),
    source_url TEXT,
    published_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    raw_payload_ref TEXT,
    content_hash TEXT,
    provenance JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS source_records_scoped_external_id_unique
    ON canonical.source_records (namespace, external_id,
        COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid));

CREATE TABLE IF NOT EXISTS canonical.entities (
    id UUID PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'therapeutic_asset', 'target', 'disease', 'indication', 'biomarker',
        'company', 'clinical_trial', 'publication', 'patent', 'regulatory_event',
        'mechanism', 'combination', 'resistance_mechanism'
    )),
    preferred_name TEXT NOT NULL CHECK (length(trim(preferred_name)) > 0),
    normalized_name TEXT NOT NULL CHECK (length(trim(normalized_name)) > 0),
    description TEXT,
    modality TEXT CHECK (modality IS NULL OR modality IN (
        'SMALL_MOLECULE', 'ANTIBODY', 'ADC', 'PROTEIN', 'PEPTIDE',
        'CELL_THERAPY', 'GENE_THERAPY', 'RNA_THERAPY', 'RADIOPHARMACEUTICAL',
        'VACCINE', 'OTHER'
    )),
    lifecycle_status TEXT,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS entities_type_created_idx
    ON canonical.entities (entity_type, created_at DESC);
CREATE INDEX IF NOT EXISTS entities_attributes_gin_idx
    ON canonical.entities USING GIN (attributes);

CREATE TABLE IF NOT EXISTS canonical.identifiers (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE CASCADE,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    namespace TEXT NOT NULL CHECK (length(trim(namespace)) > 0),
    identifier_type TEXT NOT NULL CHECK (length(trim(identifier_type)) > 0),
    value TEXT NOT NULL CHECK (length(trim(value)) > 0),
    normalized_value TEXT NOT NULL CHECK (length(trim(normalized_value)) > 0),
    source_record_id UUID NOT NULL REFERENCES canonical.source_records(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS identifiers_scoped_value_unique
    ON canonical.identifiers (namespace, identifier_type, normalized_value,
        COALESCE(organization_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX IF NOT EXISTS identifiers_entity_idx ON canonical.identifiers (entity_id);

CREATE TABLE IF NOT EXISTS canonical.aliases (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE CASCADE,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    value TEXT NOT NULL CHECK (length(trim(value)) > 0),
    normalized_value TEXT NOT NULL CHECK (length(trim(normalized_value)) > 0),
    alias_type TEXT NOT NULL CHECK (alias_type IN ('development', 'generic', 'brand', 'alias', 'synonym')),
    verification_state TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (verification_state IN ('unreviewed', 'verified', 'rejected')),
    source_record_id UUID NOT NULL REFERENCES canonical.source_records(id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ,
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS aliases_lookup_idx ON canonical.aliases (normalized_value, entity_id);
CREATE INDEX IF NOT EXISTS aliases_entity_idx ON canonical.aliases (entity_id);

CREATE TABLE IF NOT EXISTS canonical.relationships (
    id UUID PRIMARY KEY,
    subject_entity_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE RESTRICT,
    predicate TEXT NOT NULL CHECK (predicate ~ '^[A-Z][A-Z0-9_]{0,63}$'),
    object_entity_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE RESTRICT,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (subject_entity_id <> object_entity_id),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS relationships_subject_idx ON canonical.relationships (subject_entity_id, predicate);
CREATE INDEX IF NOT EXISTS relationships_object_idx ON canonical.relationships (object_entity_id, predicate);

CREATE TABLE IF NOT EXISTS canonical.observations (
    id UUID PRIMARY KEY,
    entity_id UUID NOT NULL REFERENCES canonical.entities(id) ON DELETE RESTRICT,
    relationship_id UUID REFERENCES canonical.relationships(id) ON DELETE RESTRICT,
    property_name TEXT NOT NULL CHECK (length(trim(property_name)) > 0),
    observation_kind TEXT NOT NULL CHECK (observation_kind IN (
        'source_fact', 'normalized_observation', 'hypothesis'
    )),
    value JSONB NOT NULL,
    verification_state TEXT NOT NULL DEFAULT 'unreviewed'
        CHECK (verification_state IN ('unreviewed', 'verified', 'rejected')),
    confidence DOUBLE PRECISION CHECK (confidence IS NULL OR confidence BETWEEN 0 AND 1),
    source_record_id UUID NOT NULL REFERENCES canonical.source_records(id) ON DELETE RESTRICT,
    valid_from TIMESTAMPTZ,
    valid_to TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    observed_at TIMESTAMPTZ,
    source_updated_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    normalizer_version TEXT,
    manually_verified_by UUID,
    manually_verified_at TIMESTAMPTZ,
    supersedes_observation_id UUID REFERENCES canonical.observations(id) ON DELETE RESTRICT,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (valid_from IS NULL OR valid_to IS NULL OR valid_from <= valid_to),
    CHECK (relationship_id IS NULL OR observation_kind <> 'hypothesis' OR verification_state = 'unreviewed'),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS observations_entity_time_idx ON canonical.observations (entity_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS observations_relationship_idx ON canonical.observations (relationship_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS observations_source_idx ON canonical.observations (source_record_id);

CREATE TABLE IF NOT EXISTS canonical.projection_outbox (
    id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type IN ('entity.upserted', 'relationship.upserted')),
    aggregate_id UUID NOT NULL,
    visibility TEXT NOT NULL CHECK (visibility IN ('global', 'tenant')),
    organization_id UUID,
    payload JSONB NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((visibility = 'global' AND organization_id IS NULL) OR
           (visibility = 'tenant' AND organization_id IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS projection_outbox_pending_idx
    ON canonical.projection_outbox (available_at, id) WHERE delivered_at IS NULL;

CREATE OR REPLACE FUNCTION canonical.reject_observation_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'canonical observations are append-only; insert a superseding observation';
END;
$$;
DROP TRIGGER IF EXISTS observations_are_append_only ON canonical.observations;
CREATE TRIGGER observations_are_append_only
    BEFORE UPDATE OR DELETE ON canonical.observations
    FOR EACH ROW EXECUTE FUNCTION canonical.reject_observation_mutation();

DO $$
DECLARE
    table_name TEXT;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'source_records', 'entities', 'identifiers', 'aliases',
        'relationships', 'observations', 'projection_outbox'
    ] LOOP
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
