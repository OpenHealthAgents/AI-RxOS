# Phase 2 B10: End-to-End Canonical Flow

## Golden Flow

B10 validates the existing repository path:

```text
source record
  -> B01 exact reconciliation
  -> canonical PostgreSQL entity, identifier, observation, relationship
  -> transactional projection outbox
  -> tenant-scoped projection worker
  -> Neo4j CanonicalEntity/CANONICAL_RELATIONSHIP
  -> OpenSearch canonical document
  -> Search and KG graph APIs
```

The B10 fixture is disposable and source-tagged as synthetic. It creates a
public target and a Tenant A therapeutic asset, resolves the asset by its
namespaced identifier through reconciliation, attaches a source-fact
observation, and creates a `TARGETS` relationship. The worker projects the
records without direct writes to either derived store.

## Assertions

The integration suite verifies canonical IDs, entity types, visibility,
organization ownership, source record IDs, identifier namespace/value,
observation timestamps, relationship identity, outbox event type and scope,
Neo4j endpoint/relationship identity, and Search canonical identity. It also
checks that Tenant B cannot search Tenant A's asset, an unscoped Search request
returns `401`, and the authenticated Tenant A graph API returns the projected
relationship.

A cross-tenant relationship attempt is rejected by the canonical repository and
does not add a relationship outbox event. Public target visibility remains
available to the authorized tenant. Search uses the B08 scope contract and
Neo4j uses the B07 scope contract.

## Consistency and Recovery

B09's deterministic IDs, leased outbox claims, retry/backoff, dead-letter state,
and projection version guards remain the consistency boundary. Replaying an
entity or relationship is idempotent. PostgreSQL mutations and outbox creation
remain one transaction; derived-store failures leave canonical state intact and
leave projection work retryable.

Canonical update/delete APIs are not currently part of the repository surface,
so B10 does not invent update or tombstone behavior. The existing B09 stale
version and replay tests cover projection ordering; B10 validates the current
create/reconcile/project/read lifecycle.

## Live Validation

Run the live test inside the Compose network so Search remains internal-only:

```text
docker compose run --rm --no-deps \
  -e KG_TEST_DATABASE_URL=postgresql://...@postgres:5432/ai_rxos \
  -e KG_TEST_NEO4J_URI=bolt://neo4j:7687 \
  -e KG_TEST_SEARCH_URL=http://search:8084 \
  -e KG_TEST_KG_URL=http://kg:8083 \
  -e KG_TEST_SEARCH_INTERNAL_TOKEN=... \
  -v <repo>:/workspace -w /workspace/services/kg kg \
  python -m pytest tests/test_b10_end_to_end.py -q
```

The current live run passed: `1 passed`, with the existing pytest-asyncio
fixture-scope warning only.
