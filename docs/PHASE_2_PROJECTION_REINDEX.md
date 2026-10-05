# Phase 2 B09: Canonical Projection and Reindex

## Source of Truth

Canonical PostgreSQL remains authoritative. Neo4j and OpenSearch are derived,
rebuildable projections. Canonical entity and relationship creation writes its
projection outbox row in the same PostgreSQL transaction as the canonical
mutation. Observation rows remain canonical evidence and do not independently
create projection events.

## Delivery

`CanonicalProjectionWorker` claims leased outbox rows with PostgreSQL
`FOR UPDATE SKIP LOCKED`, projects Neo4j first and Search second, and marks the
row delivered only after both succeed. Failed rows receive bounded exponential
backoff. After ten attempts they receive `dead_lettered_at` and remain visible
for investigation instead of retrying forever. Lease expiry makes a crashed
worker's claim available again.

The worker is available as:

```text
python -m app.commands.projection_worker [--once] [--limit N]
```

A shared `SEARCH_INTERNAL_TOKEN` is required for global KG-to-Search
projection. Tenant-scoped worker runs use `--organization-id`; they never use
the event payload as authorization. Compose passes the token to KG and Search,
while Search remains internal-only and Helm exposes it as `ClusterIP`.

## Mapping

Canonical entity UUIDs are used as both Neo4j `CanonicalEntity.id` and the
OpenSearch document ID. Entity type, preferred name, description, modality,
lifecycle status, attributes, tenant ownership, aliases, identifiers, and a
projection version are carried into the projections. Canonical relationship
UUIDs are used as `CANONICAL_RELATIONSHIP.id` with stable subject/object IDs.

Projection versions use the canonical replay timestamp when reindexing and the
outbox event ID for ordinary mutation events. Neo4j guards updates by version;
OpenSearch uses `version_type=external_gte`. Older events cannot overwrite
newer projection state, while an equal-version replay remains idempotent.

## Reindex

`canonical_reindex` reads canonical PostgreSQL rows and creates fresh outbox
work; it never reads Neo4j or OpenSearch:

```text
python -m app.commands.canonical_reindex
python -m app.commands.canonical_reindex --entity-type target
python -m app.commands.canonical_reindex --organization-id <uuid>
```

The current deployment does not use aliases. Reindex is therefore an additive,
resumable replay into the existing shared index rather than an atomic alias
swap. Deterministic IDs and external versions prevent duplicate or stale
projection documents. Tenant-scoped replay includes public and requested-tenant
canonical rows and does not select another tenant's rows.

## Scope and Limitations

The existing canonical model projects all supported entity types and canonical
relationships. Raw observations and provenance remain in PostgreSQL; selected
source identity is carried as identifier/alias metadata, while the canonical
source record remains authoritative. Hard deletion is not currently part of the
canonical API, so no destructive projection delete is invented in B09.

The one-shot worker and replay command support restart and partial catch-up.
Per-target delivery history, atomic index replacement, and a separate durable
projection metrics service are not introduced; the outbox row records attempts,
last error, delivery, and dead-letter state. Broader end-to-end consumer flows
remain outside B09.

## Validation

Validated during implementation:

- KG full suite: 109 passed, with infrastructure-dependent skips reported by pytest.
- Search full tests and build passed.
- Live OpenSearch B08 isolation matrix passed.
- Live Compose-network canonical PostgreSQL to Neo4j/Search projection passed.
- Live canonical reindex queued 35 events; the worker delivered 32 global events
  and correctly left tenant-private events pending without tenant scope.
- Python compilation and migration tests passed.

The remaining skips are existing infrastructure-dependent tests. Live tenant
replay should be run with an explicit organization scope and the configured
internal token.
