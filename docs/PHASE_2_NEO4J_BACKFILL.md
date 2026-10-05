# Phase 2 Neo4j Backfill

## Scope

B03 migrates actual legacy biomedical nodes from the existing KG Neo4j database into canonical PostgreSQL. Neo4j is treated as a migration source only; PostgreSQL remains authoritative.

## Actual Source Schema

The existing KG write path supports `Gene`, `Protein`, `Disease`, `Drug`, `Target`, `Mutation`, `Publication`, `Patent`, `ClinicalTrial`, `Company`, `Conference`, and `Biomarker` labels. Nodes use `id`, `name`, `description`, `source`, `metadata`, `created_at`, `updated_at`, and `version`; legacy records may additionally carry `source_id`, `external_id`, `aliases`, `visibility`, `organization_id`, or `tenant_id`.

The live development graph also contains `CanonicalEntity` and `GraphVersion` nodes plus `CANONICAL_RELATIONSHIP` projection edges. B03 explicitly excludes those projection/bookkeeping records so canonical data is not re-ingested as legacy data. Legacy relationships are read by type and preserve their Neo4j relationship ID and properties.

## Flow

`app.services.backfill.neo4j_records` normalizes nodes and preserves Neo4j ID, labels, properties, aliases, identifiers, tenant, and provenance. `app.services.neo4j_backfill` sends each record through B01 `CanonicalRepository.reconcile_legacy_record`, then persists identifiers and factual observations through the canonical repository.

Relationships are processed only after endpoint reconciliation. Ambiguous or unresolved endpoints are recorded as failures and not linked. Cross-tenant edges are rejected by the adapter. Supported resolved edges use the existing canonical relationship repository and source provenance.

## Invocation

From `services/kg`:

```powershell
$env:DATABASE_URL = "postgresql://..."
$env:NEO4J_URI = "bolt://localhost:7687"
$env:NEO4J_USER = "neo4j"
$env:NEO4J_PASSWORD = "..."
python -m app.commands.neo4j_backfill --dry-run
python -m app.commands.neo4j_backfill --apply --create-if-unresolved
python -m app.commands.neo4j_backfill --status
```

Tenant runs require `NEO4J_BACKFILL_ORGANIZATION_ID` and `NEO4J_BACKFILL_USER_ID`. Checkpoints reuse the B02 `CheckpointStore` and default to `data/neo4j-backfill.json`.

## Guarantees

- Dry-run performs Neo4j reads and B01 reconciliation without canonical writes.
- Apply uses explicit B01 creation policy for unresolved nodes.
- Malformed nodes retain their Neo4j source ID in recorded failures and do not stop later nodes.
- Repeated apply reuses B01 matches and idempotent identifier/observation/relationship persistence.
- Tenant-scoped reads include public and active-tenant nodes only; unscoped runs include public nodes only.
- `CanonicalEntity`, `GraphVersion`, and `CANONICAL_RELATIONSHIP` projection data is excluded.
- Unsupported labels and unknown private ownership are reported as failures rather than mapped or merged.

## Validation

Focused B03 tests are in `services/kg/tests/test_neo4j_backfill.py`. Live validation used the existing Compose Neo4j and PostgreSQL services with deterministic Target/Disease, malformed-node, tenant-A/B, and relationship fixtures. The first apply created two global entities and one relationship; a fresh-checkpoint replay returned exact matches and stable counts. Tenant-A apply created only tenant-A data and did not migrate the A-to-B edge.

Known limitation: the current live graph had no pre-existing legacy biomedical nodes before the deterministic validation fixture; it contained only canonical projection and graph-version records, which are intentionally excluded.
