# Phase 2 Completion Status

## Phase 2 objective

Phase 2 establishes the canonical, tenant-safe, source-backed data foundation for AI-RxOS. The objective is not a replacement architecture; it is the additive, migration-backed canonical layer in the existing model: raw/legacy evidence -> source records -> reconciliation -> canonical entities -> observations/identifiers -> canonical relationships -> outbox -> Neo4j/OpenSearch projections -> tenant-safe search and graph access.

## Architecture implemented

The repository implements the canonical owner in `services/kg` with Postgres as the authoritative system of record, Neo4j and OpenSearch as rebuildable projections, and the existing `services/search` and `services/kg` APIs as the retrieval surfaces. Source records, canonical entities, identifiers, aliases, observations, relationships, and projection outbox entries are stored in the shared PostgreSQL `canonical` schema. The projection worker emits stable, idempotent events that are projected to Neo4j and OpenSearch without overwriting PostgreSQL as the source of truth.

## B01-B11 status

| ID | Requirement | Status | Evidence |
| --- | --- | --- | --- |
| B01 | Legacy source to canonical reconciliation | COMPLETE | KG canonical repository and reconciliation live tests pass against Postgres |
| B02 | Historical literature backfill | COMPLETE | Literature canonical backfill path validated in repository suite |
| B03 | Legacy Neo4j backfill | COMPLETE | Backfill and migration behavior validated in KG suite |
| B04 | Migration validation | COMPLETE | Disposable Postgres migration tests pass; checksum drift and transactional recovery validated |
| B05 | PostgreSQL tenant isolation | COMPLETE | Live tenant-scope tests pass under PG RLS and repository checks |
| B06 | Legacy tenant enforcement | COMPLETE | Legacy enforcement tests pass in literature/PG path |
| B07 | Neo4j tenant isolation | COMPLETE | KG graph access tests pass under tenant-scoped queries |
| B08 | OpenSearch tenant isolation | COMPLETE | Search tenant-scoped retrieval validated with live local Search service |
| B09 | Projection / reindex | COMPLETE | Outbox replay and reindex behavior validated |
| B10 | End-to-end canonical flow | COMPLETE | Live B10 flow passes against real Postgres + Neo4j + Search |
| B11 | Deployment / runtime validation | COMPLETE WITH DOCUMENTED LIMITATION | Docker Compose stack is healthy, Search host port fixed, Auth/runtime role corrected, Helm lint passes |

## B12 final closure status

Status: COMPLETE WITH DOCUMENTED LIMITATION

This means the Phase 2 implementation and validation are complete for the repository’s tested runtime architecture, but the project is not being claimed as broadly production-ready or clinical-grade. The repository-level acceptance criteria for Phase 2 have been satisfied for the actual runtime scenarios exercised in this environment.

## Canonical data model

The canonical model is implemented in `services/kg/app/schemas/canonical.py` and `services/kg/app/services/canonical_repository.py`. It includes:

- source records with provenance and immutable identity metadata;
- canonical entities with explicit entity types and visibility scopes;
- namespaced identifiers and aliases with normalization and ambiguity rules;
- append-only observations with valid time and provenance metadata;
- canonical relationships with endpoint validation and visibility constraints;
- projection outbox entries for transactional replay to derived stores.

Deterministic identity and idempotency are enforced through exact namespaced identifier resolution, normalized lookup rules, and uniqueness constraints in Postgres. Duplicate same-name records remain valid and resolve as ambiguous; they do not get silently merged.

## Evidence/provenance

Evidence provenance is preserved at every layer:

- source records store namespace, external id, source type, URL, observed/published timestamps, and raw payload metadata;
- identifiers and aliases reference source records;
- observations include source_record_id, confidence, valid_from/valid_to, revision metadata, and reviewer information where applicable;
- canonical relationships are created from source-backed observations and remain tenant-scoped.

The live repository tests confirm provenance survives the canonical lifecycle and outbox projection path.

## Tenant isolation

Tenant isolation was validated against the repo’s real PostgreSQL environment:

- public data remains readable by authorized callers;
- tenant A cannot read or mutate tenant B data;
- missing/invalid tenant scope fails closed;
- cross-tenant relationship creation is rejected;
- Neo4j and OpenSearch read paths are scope-filtered and exposed only through the authorized canonical and search APIs.

The repo’s Postgres and graph/search validation paths prove this behavior under real local services.

## PostgreSQL

The PostgreSQL side remains authoritative for canonical state. Its validated invariants include:

- additive migration ordering and checksums;
- forced RLS and app-level tenant filters;
- non-superuser runtime role enforcement (`ai_rxos_app` is non-superuser and non-BYPASSRLS);
- transactional projection outbox events;
- migration drift detection and repeatability;
- append-only observations and source-linked records.

The earlier canonical test issue (duplicate/outbox contamination via reused DB state) was fixed by isolating each canonical live test with a fresh disposable Postgres database.

## Neo4j

Neo4j is a derived projection layer, not the system of record. The canonical projection worker publishes entity and relationship events to Neo4j using stable IDs and projection-version semantics. The live Phase 2 path verifies graph projection, tenant isolation, and relationship traversal under the real service stack.

## OpenSearch

OpenSearch remains a derived search projection. The live Search endpoint is now published on its required host port (`8084`), and the real KG projection tests pass against it. Search retrieval respects tenant scoping and fails closed when the caller lacks the required organization context.

## Outbox

The canonical outbox is transactional and replayable. The repository validates:

- transactional creation of outbox events;
- idempotent project/reproject behavior;
- tenant-scoped event claiming and delivery;
- bounded retry with backoff and dead-letter semantics;
- worker restart and reindex safety.

## Projection/reindex

The projection and reindex path is built around the canonical outbox and is deterministic. Repeated event processing does not create duplicates in canonical data, and the repository’s projection tests cover Neo4j and Search replay behavior under the actual stack.

## Search/graph

The repo passes the implemented live graph and search validation path:

- graph projection is created and retrieved from Neo4j;
- Search API returns canonical results scoped to the correct organization;
- cross-tenant search does not leak data;
- unscoped access fails closed;
- canonical API retrieval remains authoritative.

## Deployment

Docker Compose and runtime validation were fixed and rerun:

- Search service now publishes `8084:8084`;
- PostgreSQL runtime role is configured as a non-superuser;
- Auth and service startup is healthy;
- `helm lint` passes for the repo chart;
- the real local runtime stack is healthy enough to support the KG and Search validation path.

## Security

Phase 2 security validation is engineering-grade and repository-scoped. It includes explicit JWT verification, organization scope enforcement, fail-closed access patterns, RLS constraints, and denial of cross-tenant data access. This does not claim production or clinical compliance beyond the tested repository/runtime boundaries.

## Testing

Executed and passed:

- `python -m pytest -q services/kg/tests/test_phase_3_and_4.py` → 2 passed
- `python -m pytest -q services/kg/tests/test_canonical.py` → 7 passed
- `python -m pytest -q services/kg/tests` → 83 passed, 2 skipped before enabling live env; final live env re-run after fixing Search port returned 2 live end-to-end tests passed and the full KG suite passed
- `cd services/literature; python -m pytest -q` → 109 passed
- `cd services/search; go test ./...` → passed
- `git diff --check` → passed

## Known non-blocking limitations

The only remaining limitations are explicit and documented, not hidden:

- Phase 2 is validated for the repository’s runtime scenarios, not for broad production or clinical deployment;
- some future domain workloads (e.g., temporal evidence, advanced policy engines, deeper production ops) remain explicitly out of scope for this Phase 2 closure;
- deployment and service configuration remain environment-specific and should be treated as repo/runtime assumptions, not shared infrastructure guarantees.

## Phase 3/4 compatibility

The Phase 3/4 evidence and temporal features are additive and do not break the Phase 2 canonical foundation. The repository validated both the Phase 3/4 live tests and the Phase 2 canonical regression suites under the same Postgres-backed runtime path.

## Production readiness state

Phase 2 platform architecture is implemented and validated for the tested repository/runtime scenarios.

It is not broad production-ready in a regulatory, clinical, or operational sense; it is complete for the repository’s canonical, tenant-safe, source-backed architectural requirements as exercised in the current local runtime environment.
