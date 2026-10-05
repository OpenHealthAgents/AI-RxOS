# Phase 2 B06 — Legacy Tenant Enforcement

## Status

**PHASE 2 B06 — COMPLETE**

B06 closes the legacy PostgreSQL escape hatch for the literature service and B02
literature replay. Canonical PostgreSQL isolation from B05 remains unchanged.

## Audited legacy tables

| Table | Ownership | Access paths | Enforcement |
| --- | --- | --- | --- |
| `literature_papers` | `tenant_id` is tenant-private; `NULL` is public/shared | Literature paper list/detail APIs; KG B02 replay | PostgreSQL RLS plus transaction-local `app.literature_organization_id`; public rows are visible to active tenants, private rows require the matching tenant; unscoped callers see public rows only |
| `literature_ingestion_jobs` | `organization_id` is tenant-private; `NULL` is system/public legacy state | Ingestion API, orchestrator worker/scheduler, retry/cancel/dead-letter paths | PostgreSQL RLS plus the same transaction-local context; API-created jobs carry the authenticated organization; scheduler uses explicit system scope and then persists each job with its own organization |

The legacy literature schema does not contain separate PostgreSQL entity or
relationship tables. Extracted entities and relationships are JSON payloads on
`literature_papers` and therefore inherit paper-row isolation. The canonical
entity, relationship, source, observation, and reconciliation tables are in the
B05 `canonical` schema and are not modified by B06.

## Enforcement rules

- Tenant context comes from the verified authentication claim through
  `get_tenant_context`; request parameters do not choose a tenant.
- `PostgresManager.acquire(organization_id)` sets transaction-local context and
  `FORCE ROW LEVEL SECURITY` applies it to both legacy tables.
- Missing tenant context is fail-closed for private rows. Public rows remain
  available according to the documented public/shared rule.
- System-wide scheduler and migration operations must set the explicit
  `app.literature_system_scope` flag. Missing context alone never grants
  all-tenant access.
- B02 replay sets both GUCs on its raw pool connection. Tenant replay uses the
  tenant scope; operator replay without a tenant explicitly uses system scope.
- Job reload, retry, cancellation, persistence, and dead-letter lookup retain
  the job organization. Scheduler discovery is the only all-tenant operation.

## Attack matrix

| Operation | Tenant A -> A | Tenant A -> B | Tenant B -> A | No tenant -> private | Public |
| --- | --- | --- | --- | --- | --- |
| Paper SELECT / identifier lookup | allow | deny | deny | deny | allow |
| Job SELECT | allow | deny | deny | deny | system-only for system rows |
| Paper/job UPDATE or DELETE | allow | deny | deny | deny | policy-dependent public/system operation |
| B02 replay input | A only | deny | deny | deny unless explicit system scope | allow |
| Extracted entity/relationship JOIN through paper | A only | deny | deny | deny | public only |
| Batch/scheduler access | job tenant only | deny | deny | deny | explicit system scope |

## Compatibility

- B01 reconciliation remains the canonical boundary and still returns
  `EXACT_MATCH`, `POSSIBLE_MATCH`, `AMBIGUOUS`, `UNRESOLVED`, and `NEW_ENTITY`
  without resolving against another tenant's private canonical records.
- B02 retains `public + active tenant` literature visibility and now applies the
  same scope to the raw backfill connection.
- B03/B04 Neo4j tenant behavior is unchanged.
- B05 canonical PostgreSQL RLS, transaction-local context, and checksum-tracked
  migrations are unchanged.

## Validation

Focused executable validation completed:

- KG B02 backfill tests: 12 passed.
- Literature orchestration tests: 7 passed.
- Live non-superuser legacy attack matrix: 1 passed.
- Live B06 matrix plus focused Literature checks: 9 passed.
- Fresh-database full KG suite: 79 passed, 1 skipped.
- Full Literature suite: 109 passed.
- Python compilation for `services/kg/app` and `services/literature/app` passed.
- `git diff --check` passed.

The live attack matrix used a disposable database and a dedicated
`NOSUPERUSER NOBYPASSRLS` role. It verified public/A/B reads, cross-tenant
updates/deletes, spoofed inserts, no-tenant fail-closed behavior, RLS metadata,
and transaction-local pool reuse for both legacy tables.

## Known exceptions

The literature service's in-memory fallback is retained for its existing test
and degraded-mode behavior. It has no durable cross-tenant database rows; a
production deployment must use PostgreSQL for tenant-sensitive operation.
