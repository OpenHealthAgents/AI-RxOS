# Phase 2 Implementation Record

## Status

**PHASE 2 — NOT COMPLETE**

The canonical persistence/API foundation is implemented incrementally in existing owners. B02 historical literature backfill, B03 legacy Neo4j backfill, B04 migration validation, B05 PostgreSQL tenant isolation, B06 legacy application-path enforcement, and B07 Neo4j tenant isolation are implemented in the existing owners. Phase 3 has not started.

## Existing Implementation Reused

- `services/kg` remains the FastAPI and Neo4j owner; its current graph routes, labels, version service, and Compose service are preserved.
- The repository's existing shared PostgreSQL instance is reused; no second database, canonical service, or parallel graph/search owner was introduced.
- `services/literature` remains the acquisition and publication parsing owner. Its PMID/PMCID/DOI and NCT source identifiers are migration inputs; no existing literature rows were rewritten.
- `services/search` remains the OpenSearch owner. The existing index endpoint and document ID are extended with canonical metadata.
- `services/auth` remains the identity owner. Canonical routes independently verify its HS256 bearer-token convention and derive organization/user scope only from JWT claims.
- Existing `packages/types` is extended with shared Zod wire contracts.

## Changed and Newly Implemented

- KG-owned `canonical` PostgreSQL schema for entity identity, modality, scoped visibility, source records, namespaced identifiers, aliases, relationships, observations, and a projection outbox.
- Exact NFKC/case/whitespace normalization separated from resolution. Names do not uniquely identify records. Multiple same-name entities remain distinct and resolve as `ambiguous`; unreviewed aliases remain candidates; verified aliases and exact namespaced IDs may resolve.
- Typed extensible entity attributes cover asset, target, disease, indication, biomarker, company, clinical trial, publication, patent, regulatory event, mechanism, combination, and resistance mechanism. Modalities include all requested categories from small molecule through `OTHER`.
- Append-only source-linked observations support source/normalized/hypothesis kind, review state, confidence, valid time, publication/source update/observation/ingestion timestamps, normalizer version, reviewer UUID/time, and supersession. Initial lifecycle status is stored as an observation.
- Forced PostgreSQL RLS plus repository visibility predicates enforce global-or-own-organization reads. Tenant relationships/observations can annotate global entities privately. Client payloads never choose organization IDs.
- Canonical FastAPI routes are added to KG and `/api/v1/canonical` is routed by the existing Go gateway.
- An outbox worker projects global records idempotently to existing Neo4j/Search owners. Claims use a lease and `SKIP LOCKED`; failures use bounded backoff. Tenant events remain in PostgreSQL pending downstream tenant-safe read enforcement.
- Search document schema now accepts `canonical_id` and `entity_type`; failed Search indexing returns upstream failure instead of false success.
- The idempotent demo seed creates 16 entities and 10 sourced relationships as synthetic fixtures. Every source record is labeled `synthetic`; every edge is an unreviewed hypothesis. It asserts no real trial, publication, patent, regulatory decision, or efficacy claim.
- B02 literature backfill replays the existing `literature_papers` store through B01, with dry-run/apply/status modes, durable checkpoints, idempotent identifiers/observations/relationships, source provenance, failure isolation, and source-level tenant filtering. See [PHASE_2_LITERATURE_BACKFILL.md](PHASE_2_LITERATURE_BACKFILL.md).
- B03 legacy Neo4j backfill reads actual legacy labels/properties, excludes canonical projections and bookkeeping nodes, reuses B01, preserves Neo4j lineage, migrates factual observations and safe relationships, and uses tenant-scoped durable checkpoints. See [PHASE_2_NEO4J_BACKFILL.md](PHASE_2_NEO4J_BACKFILL.md).
- B04 validates clean/repeated migration, existing canonical data, transactional failure recovery, append-only integrity, foreign keys, RLS policies, and migration checksums in disposable PostgreSQL databases. See [PHASE_2_MIGRATION_VALIDATION.md](PHASE_2_MIGRATION_VALIDATION.md).
- B05 proves direct PostgreSQL RLS isolation for public, Tenant A, Tenant B, unscoped reads/writes, reconciliation/source records, and transaction-local pooled tenant context. See [PHASE_2_POSTGRES_TENANT_ISOLATION.md](PHASE_2_POSTGRES_TENANT_ISOLATION.md).
- B06 carries authenticated organization scope through legacy literature reads, ingestion jobs, scheduler/retry/cancel paths, and the raw B02 replay connection. Legacy RLS and the attack matrix are documented in [PHASE_2_LEGACY_TENANT_ENFORCEMENT.md](PHASE_2_LEGACY_TENANT_ENFORCEMENT.md).
- B07 makes Neo4j scope explicit at the KG Cypher callback boundary, protects both relationship endpoints and traversal paths, disables arbitrary Cypher, protects canonical projection ownership, and preserves scoped B03 reads. See [PHASE_2_NEO4J_TENANT_ISOLATION.md](PHASE_2_NEO4J_TENANT_ISOLATION.md).
- B08 hardens the existing Search owner with immutable per-operation OpenSearch/QMD scope, public/organization/workspace visibility filters, fail-closed HTTP reads, tenant-derived bulk writes, and focused regression/live-test coverage. See [PHASE_2_OPENSEARCH_TENANT_ISOLATION.md](PHASE_2_OPENSEARCH_TENANT_ISOLATION.md). Live OpenSearch validation remains required before B08 can be marked complete.
- B09 extends the existing canonical PostgreSQL outbox into a leased, retryable Neo4j/Search projection worker and adds canonical-source replay commands. Deterministic IDs, projection versions, bounded dead-letter retries, explicit Search authentication, and tenant-scoped replay preserve PostgreSQL authority. See [PHASE_2_PROJECTION_REINDEX.md](PHASE_2_PROJECTION_REINDEX.md).
- B09 validation: KG `109 passed`, Search tests/build passed, the live Compose-network entity and relationship projection passed, live OpenSearch tenant isolation passed, repeated canonical target reindex completed without duplicate projection errors, and tenant-scoped delivery drained tenant events.
- B10 validates the live source-to-reconciliation-to-canonical-to-outbox-to-Neo4j/OpenSearch-to-Search/graph flow, including identifiers, observations, provenance, tenant isolation, public visibility, and cross-tenant relationship rejection. See [PHASE_2_END_TO_END_CANONICAL_FLOW.md](PHASE_2_END_TO_END_CANONICAL_FLOW.md).
- B11 deployment validation is in progress and currently **NOT COMPLETE**: Auth remains blocked by a stale image/runtime dependency failure, the live PostgreSQL runtime role is superuser/BYPASSRLS, and Helm CLI validation is unavailable. See [PHASE_2_DEPLOYMENT_VALIDATION.md](PHASE_2_DEPLOYMENT_VALIDATION.md).

## Migrations

All are under `services/kg/migrations/` and are tracked by the KG migration runner under a PostgreSQL advisory lock:

1. `001_canonical_data_model.sql`: additive schema, constraints/indexes, RLS policies, append-only observation trigger, and outbox.
2. `009_projection_retry_and_replay.sql`: bounded outbox attempts and visible dead-letter timestamps for projection recovery.
2. `002_decouple_auth_ownership.sql`: organization/user UUIDs remain opaque KG-owned values; no Auth-table migration-order dependency.
3. `003_allow_ambiguous_names.sql`: drops the normalized-name unique index so name collisions remain candidates, not rejected/merged entities.
4. `004_record_verification_actor.sql`: reviewer identity/time constraints for verified aliases.
5. `005_entity_source_provenance.sql`: source-record FK for entity creation provenance.
6. `006_reconciliation_results.sql`: B01 reconciliation result storage and scoped uniqueness.
7. `007_migration_checksums.sql`: migration checksum metadata and applied-time index.
8. `008_reconciliation_tenant_policy.sql`: reconciliation-results RLS policy.

No existing Auth or Wiki records were backfilled or deleted. B02 and B03 are additive migrations; source rows and legacy Neo4j nodes are preserved. Migrations are intentionally forward-only; B04 validates transactional recovery instead of destructive rollback against append-only data.

## APIs

Implemented in `services/kg/app/routers/canonical.py`:

- `GET/POST /api/v1/canonical/entities` and `GET /api/v1/canonical/entities/{entity_id}`
- `GET/POST` collection routes and `GET /{entity_id}` detail routes for assets, targets, diseases, indications, biomarkers, companies, trials, publications, patents, regulatory events, mechanisms, combinations, and resistance mechanisms
- `GET /api/v1/canonical/resolve` for namespaced identifiers and `GET /api/v1/canonical/resolve-name` for exact normalized names
- `GET/POST /api/v1/canonical/relationships`
- `POST /api/v1/canonical/observations` and `GET /api/v1/canonical/entities/{entity_id}/observations`

`docs/API_SPEC.md` records these implemented endpoints. Existing `/api/v1/graph` APIs are unchanged.

## Validation

- All eight canonical migrations applied and tracked in disposable PostgreSQL databases; the live Compose database records migrations 001-008 with checksums and the reconciliation RLS policy.
- Full KG suite: **50 passed** against disposable Postgres plus live Neo4j/Search projection services; one existing pytest-asyncio fixture-loop-scope deprecation warning. Coverage includes modality/schema validation, normalization, JWT verification/rejection, migrations, source/identifier/alias provenance, ambiguous name resolution, duplicate identity preservation, reviewer audit metadata, append-only/lifecycle observations, tenant isolation, private annotations on global entities, outbox concurrency, HTTP routes, and live projection.
- `pnpm --filter @ai-rxos/auth test`: 62 passed across 16 files; Auth typecheck/build passed.
- Search `go test ./...` / `go build ./...`, Gateway `go test ./...` / `go build ./...`, and `pnpm --filter @ai-rxos/types build` passed. Web/Admin typechecks passed.
- The demo seed ran twice with stable counts: 16 source-tagged entities and 10 source-tagged relationships. All 16 entity and 10 relationship outbox events were delivered.
- Live KG query found canonical Neo4j entities across the seeded families. Live Search lookup of `DEMO-ADC-001` returned its stable `id`/`canonical_id` and `entity_type=therapeutic_asset`.
- `pnpm --filter @ai-rxos/types build`: passed after canonical Zod schema additions.
- `go test ./...` and `go build ./...` in `services/search`: passed after stable canonical document fields and error propagation.
- B04 disposable migration suite: **6 passed**; live migration upgrade and repeat invocation passed.
- `go test ./...` in `apps/api-gateway`: passed after adding the route prefix.
- `docker compose config --quiet`: passed after KG/OpenSearch/Search configuration changes.
- Final KG container image built and started; all five migration IDs are recorded. Search was rebuilt with the public demo root CA mounted, a certificate-valid hostname, TLS verification enabled, and Compose override to the supported `llm_wiki` provider.

## Legacy-to-Canonical Reconciliation (B01)

The canonical reconciliation engine is implemented as a reusable, tenant-safe service in `services/kg/app/services/canonical_repository.py` and exposed through the KG canonical API at `/api/v1/canonical/reconcile`.

The matching hierarchy follows the required deterministic priority:
1. exact namespaced identifier;
2. normalized identifier;
3. trusted source mapping metadata;
4. exact normalized alias;
5. controlled normalized-name candidate resolution;
6. ambiguous multi-candidate response;
7. unresolved record if no candidate exists.

The engine returns exactly one of `EXACT_MATCH`, `POSSIBLE_MATCH`, `AMBIGUOUS`, `UNRESOLVED`, or `NEW_ENTITY`.
It preserves source provenance, candidate IDs, and the reason for the resolution decision.
It fails closed for tenant-private reconciliation when the tenant context is missing or mismatched.

## Known Limitations and Remaining Acceptance

- Local Compose OpenSearch/Search projection now passes with explicit demo root-CA trust and TLS verification; do not reuse the demo root CA outside local development. Helm still defaults to unsupported `pgvector`, so managed/provider config needs correction/validation.
- Neo4j/Search projection is validated for global synthetic records. Tenant-private graph/search projection remains disabled until every downstream query path enforces tenant scope.
- B02 covers historical literature publications only. Trial, patent, and company records remain unmapped. B03 migrates supported legacy Neo4j nodes but does not treat canonical projection nodes as legacy input.
- Tenant-private records are correctly stored in PostgreSQL but are not projected to Neo4j/OpenSearch until every downstream search/graph read path enforces tenant scope.
- B06 direct non-superuser validation for legacy tables passes against disposable PostgreSQL; the legacy literature ownership-column policy defect found during validation was corrected without changing canonical RLS.
- Current canonical APIs are foundational. Response pagination/error conventions, OpenAPI/SDK coverage, source adapter mappings, and full API integration coverage still need review.
- Production issuer/audience configuration and the repository's wider Gateway claim-propagation/service authorization gaps remain security work; canonical endpoints do not claim to solve legacy routes.
- Full repo build retains the pre-existing Storybook React-type failure and is outside this Phase 2 implementation slice.

## Intentionally Deferred

No external ingestion connector, scientific claim, production seed claim, entity auto-merge, derived feature, prediction, decision engine, research copilot, frontend feature, or tenant-private graph/search projection was implemented. Temporal fields are available, but complete as-of reconstruction, evidence conflict workflows, derived-feature lineage, and recommendation snapshots are future work. Do not start Phase 3 until Phase 2 acceptance checks pass.
