# Phase 2 B11: Deployment Validation

## Deployment Topology

The current Compose topology uses PostgreSQL, Redis, Neo4j, OpenSearch, KG,
Search, Literature, LLM Wiki, Gateway, and auxiliary services on the
`ai-rxos` network. PostgreSQL migrations are applied by KG startup. KG hosts
the existing canonical projection loop; the B09 one-shot worker is also
available as `app.commands.projection_worker` for controlled operation.
Search is internal-only in Compose and Helm; Gateway is the intended external
API boundary.

The canonical runtime path is:

```text
PostgreSQL migrations/canonical state
  -> KG outbox/projector
  -> Neo4j and Search
  -> Gateway / Graph / Search consumers
```

## Validation Results

- `docker compose config --quiet`: passes when the required
  `SEARCH_INTERNAL_TOKEN` is supplied. Compose now fails closed if that token
  is absent.
- PostgreSQL, Redis, Neo4j, OpenSearch, KG, Search, Literature, and LLM Wiki
  containers were running during validation. PostgreSQL, Neo4j, Redis, and
  OpenSearch health checks passed.
- Search starts cleanly against the persisted legacy OpenSearch mapping after
  removing the invalid in-place mapping update. Existing text mappings are
  handled by `.keyword`-compatible tenant filters.
- Canonical migrations 001 through 009 are present in the live database.
- KG, Literature, and Search regression checks passed in their respective
  suites before deployment validation.
- The B10 live Compose-network lifecycle remains the deployment smoke path.

## Blocking Findings

1. The current Auth image is crash-looping because its stale runtime image
   cannot resolve the declared `dotenv` dependency. A Dockerfile fix was made
   to include pnpm's virtual store and module metadata, but rebuilding Auth was
   blocked by npm registry DNS/timeouts in this environment. Auth health,
   Gateway health, and authenticated end-to-end deployment behavior therefore
   remain unvalidated.
2. The live PostgreSQL `ai_rxos` role is a superuser with `BYPASSRLS`. This is
   not acceptable evidence for deployment tenant isolation. A separate
   non-superuser runtime role and migration role split is required before B11
   can be complete; no destructive role change was applied to the existing
   development volume.
3. Helm lint/template validation is environment-blocked because the `helm`
   executable is not installed. The chart was statically inspected; live Helm
   rendering and Kubernetes probes remain unvalidated.

## Configuration Requirements

- Set a non-empty `SEARCH_INTERNAL_TOKEN` in Compose or the Helm Secret/
  ExternalSecret before starting KG/Search projection flows.
- Production External Secrets must provide the key
  `ai-rxos/search-internal-token`.
- Helm now selects the implemented `llm_wiki` Search provider rather than the
  obsolete `pgvector` value.
- Development defaults for database, JWT, Neo4j, and OpenSearch credentials
  remain unsuitable for production.

## Status

B11 is **NOT COMPLETE** until Auth can be rebuilt and become healthy, runtime
PostgreSQL uses a non-superuser non-`BYPASSRLS` role, and Helm validation is
performed in an environment with the Helm CLI or an equivalent supported
renderer. No B12 or domain-engine work was started.
