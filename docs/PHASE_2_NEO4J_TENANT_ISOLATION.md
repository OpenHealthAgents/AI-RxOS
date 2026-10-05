# Phase 2 B07: Neo4j Tenant Isolation

## Model

`services/kg` owns the Neo4j graph. Legacy biomedical nodes use `visibility` and either `organization_id` or the legacy `tenant_id` property. Missing visibility is treated as global for legacy data. Canonical projection nodes use `CanonicalEntity.visibility` and `CanonicalEntity.organization_id`; canonical IDs remain PostgreSQL-owned.

A tenant scope can read global nodes and nodes owned by its organization. Relationships are visible only when both endpoints are visible in that scope. Public endpoints therefore cannot be used to reach or count private endpoints.

## Enforcement Boundary

Neo4j Community 5.26 does not provide PostgreSQL-style property RLS for this model. Enforcement is application-layer at the `services/kg/app/cypher/queries.py` callback boundary:

- every tenant-sensitive callback requires an explicit `Neo4jScope`;
- node reads, writes, lists, searches, counts, and deletes apply visibility predicates;
- relationship operations apply visibility predicates to both endpoints;
- neighbors, subgraphs, and paths require every returned/traversed node to be visible;
- arbitrary Cypher execution is disabled;
- missing scope raises `Neo4jAuthorizationError` before a query reaches Neo4j.

Ordinary API routes derive the organization only from the verified JWT principal. Request body, query parameter, header, and Cypher tenant IDs are not authority. Trusted migration/projection work must use an explicit system scope; B03 no-organization replay requires `graph:system` permission.

## Projection and Backfill

Canonical projection rejects ownership-changing updates to an existing projected entity and checks endpoint ownership before projecting relationships. B03 backfill applies the same tenant/system scope to legacy node and relationship reads. Its reconciliation, checkpoint, provenance, and ambiguity behavior remains unchanged.

## Validation

`services/kg/tests/test_neo4j_tenant_isolation.py` runs against the disposable/live Compose Neo4j when reachable. It covers public, Tenant A, and Tenant B nodes; direct reads; search; neighbors; cross-tenant paths; relationship counts; mutation and deletion attempts; cross-tenant relationship creation; cleanup; and missing-scope fail-closed behavior.

The live validation result for this implementation was 2 passed. The focused compatibility set covering B03/backfill, Cypher regressions, graph routes, and injection checks was 49 passed. Full KG validation remains the source of the final Phase 2 status.

## Limitation

This is not database-level Neo4j authorization. Callers with direct unrestricted Bolt credentials can bypass the KG application boundary. Production credentials and network policy must therefore keep Neo4j private to the KG owner and trusted migration workers.
