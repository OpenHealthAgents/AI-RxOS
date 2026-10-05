# Phase 2 PostgreSQL Tenant Isolation (B05)

## Boundary

Canonical rows with `organization_id IS NULL` are public/shared. Rows with a non-null `organization_id` are private to that organization. `canonical.reconciliation_results` uses its equivalent `tenant_id` column. The canonical PostgreSQL database is the security boundary; repository predicates are defense in depth.

The `canonical` tables protected by RLS are `source_records`, `entities`, `identifiers`, `aliases`, `relationships`, `observations`, `projection_outbox`, and `reconciliation_results`.

## Tenant Context Lifecycle

`CanonicalStore.connection(organization_id)` acquires a pooled connection, starts a transaction, and executes `set_config('app.canonical_organization_id', value, true)`. The `true` argument makes the setting transaction-local. Commit/rollback resets it before the connection returns to the pool. Unscoped connections set an empty value, and `canonical.current_organization_id()` returns NULL.

Every policy allows only public rows or rows matching the current organization. With no tenant context, private rows are invisible and private writes fail. `FORCE ROW LEVEL SECURITY` ensures table owners do not bypass the policy; B05 tests use a dedicated non-superuser role because PostgreSQL superusers bypass RLS even with `FORCE`.

## Validation

`services/kg/tests/test_postgres_tenant_isolation.py` creates disposable databases and deterministic Tenant A, Tenant B, and public fixtures covering every canonical entity type, identifiers, observations, relationships, reconciliation results, and source records. It executes direct SQL, not only repositories, and proves:

- Tenant A sees public plus A, never B.
- Tenant B sees public plus B, never A.
- Unscoped sessions see no private rows.
- Cross-tenant INSERT, UPDATE, and DELETE attempts are blocked or affect zero rows.
- Reconciliation and source records are isolated.
- Transaction-local tenant settings cannot leak through pooled connection reuse.

B02 and B03 compatibility remains covered by their existing backfill suites and post-migration smoke validation. No B01-B04 implementation was weakened.
