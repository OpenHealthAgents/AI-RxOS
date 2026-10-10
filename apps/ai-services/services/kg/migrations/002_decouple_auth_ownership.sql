-- Canonical records own organization/user UUID claims as opaque identifiers.
-- Auth remains the owner of its public.organization and public.user tables.
ALTER TABLE IF EXISTS canonical.source_records
    DROP CONSTRAINT IF EXISTS source_records_organization_id_fkey;
ALTER TABLE IF EXISTS canonical.entities
    DROP CONSTRAINT IF EXISTS entities_organization_id_fkey,
    DROP CONSTRAINT IF EXISTS entities_created_by_fkey;
ALTER TABLE IF EXISTS canonical.identifiers
    DROP CONSTRAINT IF EXISTS identifiers_organization_id_fkey;
ALTER TABLE IF EXISTS canonical.aliases
    DROP CONSTRAINT IF EXISTS aliases_organization_id_fkey;
ALTER TABLE IF EXISTS canonical.relationships
    DROP CONSTRAINT IF EXISTS relationships_organization_id_fkey;
ALTER TABLE IF EXISTS canonical.observations
    DROP CONSTRAINT IF EXISTS observations_organization_id_fkey,
    DROP CONSTRAINT IF EXISTS observations_manually_verified_by_fkey;
ALTER TABLE IF EXISTS canonical.projection_outbox
    DROP CONSTRAINT IF EXISTS projection_outbox_organization_id_fkey;
