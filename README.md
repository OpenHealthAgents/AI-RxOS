# AI-RxOS

AI-native drug discovery operating system — literature intelligence, a
knowledge graph, molecule design, and agentic workflows in one platform. This
is a Turborepo/pnpm monorepo covering the frontend, gateway, and core
services described in [`architecture/`](architecture/); the static marketing
site (`index.html`, `about.html`, `architecture.html`) lives alongside it at
the repo root and is unrelated to the application code below.

## Stack

| Layer | Tech |
|---|---|
| Monorepo | Turborepo + pnpm workspaces |
| Web frontends | Next.js 14 (App Router, TypeScript, Tailwind) |
| API Gateway | Go (chi router, JWT auth, rate limiting, reverse proxy) |
| AI / knowledge services | FastAPI (Python 3.12) |
| Relational + vector store | PostgreSQL 16 + pgvector |
| Graph store | Neo4j 5.26 |
| Cache / sessions | Redis 7 |
| Full-text + hybrid search | OpenSearch 2.19 |
| Containers | Docker (multi-stage builds, distroless Go runtime images) |
| Orchestration | Kubernetes + Helm (umbrella chart with Bitnami/Neo4j/OpenSearch dependencies) |

## Repository layout

```
apps/
  web/                Next.js — end-user app                    :3000
  admin/               Next.js — admin console                   :3001
  api-gateway/          Go — routing, auth, rate limiting          :8080
  ai-services/          FastAPI — agent orchestration facade       :8090
  knowledge-service/    FastAPI — knowledge graph BFF (Neo4j)       :8091

packages/
  ui/                  shared React components
  sdk/                  typed TS client for the gateway API
  types/                shared TS types / zod schemas
  tenancy/              multi-tenancy naming/type contract (scaffold, not yet enforced)
  audit-log/             audit-event schema + sink interface (scaffold, no backend yet)

config/
  eslint-config/, typescript-config/   shared lint/tsconfig bases

services/
  auth/                Go — identity, JWT, Postgres + Redis         :8081
  auth-adapter/         Node/TS — BetterAuth scaffold (additive)     :8089
  literature/           FastAPI — ingestion/extraction/citations     :8082
  kg/                   FastAPI — core graph CRUD (Neo4j)            :8083
  search/               Go — hybrid OpenSearch + pgvector search     :8084
  agents/               FastAPI — agent orchestrator (Redis)         :8085
  workflows/            FastAPI — multi-step workflow engine         :8086
  reports/              FastAPI — report generation                 :8087
  docking/              FastAPI — molecular docking (stub scorer)    :8088

infra/
  k8s/                 raw namespace + network-policy manifests
  helm/ai-rxos/         umbrella Helm chart for all 13 services
  postgres/init.sql     enables pgvector/uuid-ossp on first boot
```

Every `apps/*` and `services/*` unit — including the Go and Python ones — has
its own `package.json` with `dev`/`build`/`lint`/`test` scripts that shell
out to the native toolchain (`go build`, `uvicorn`, `pytest`, ...), so Turbo
can orchestrate the whole polyglot repo (`pnpm build`, `pnpm dev --parallel`,
etc.) rather than just the JS packages.

## Quickstart — Docker Compose (fastest path to a running system)

```bash
cp .env.example .env
docker compose up -d --build --wait
```

This builds and starts all 13 services plus Postgres+pgvector, Neo4j, Redis,
and OpenSearch, wired together on one network with real inter-service auth
(JWT), a real Postgres-backed user store, and a real Neo4j graph. Verified
end-to-end during development:

```bash
curl -X POST http://localhost:8080/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@ai-rxos.dev","password":"SuperSecret123","displayName":"Demo"}'
# -> {"accessToken": "...", "refreshToken": "...", "expiresIn": 900}

curl http://localhost:8080/api/v1/reports \
  -H "Authorization: Bearer <accessToken>"
# -> proxied through api-gateway to the reports service
```

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| Admin | http://localhost:3001 |
| API Gateway | http://localhost:8080 |
| Neo4j Browser | http://localhost:7474 |
| OpenSearch | http://localhost:9200 |

`docker compose down` tears the stack down; add `-v` to also drop the named
volumes (Postgres/Neo4j/Redis/OpenSearch data).

## Quickstart — local dev (no Docker)

```bash
pnpm install
pnpm dev   # runs turbo run dev --parallel across every workspace package
```

Each service still needs its own datastore reachable (point `DATABASE_URL`,
`NEO4J_URI`, `REDIS_URL`, `OPENSEARCH_URL` in `.env` at either the Compose
stack's exposed ports or your own instances).

**Windows caveat:** building `apps/web`/`apps/admin` locally via `pnpm build`
(Next.js standalone output) requires filesystem symlink permission, which
plain Windows accounts don't have by default (`EPERM: operation not
permitted, symlink`). Either enable Developer Mode / run the shell as
Administrator, or just build via Docker (`apps/web/Dockerfile`) — the actual
deployment path — which runs on Linux and is unaffected.

## Deploying to Kubernetes

See [`infra/README.md`](infra/README.md). Short version:

```bash
kubectl apply -f infra/k8s/
helm dependency update infra/helm/ai-rxos
helm install ai-rxos infra/helm/ai-rxos \
  -f infra/helm/ai-rxos/values.yaml \
  -f infra/helm/ai-rxos/values-dev.yaml \
  --create-namespace -n ai-rxos-development
```

`values-dev.yaml` spins up Postgres/Neo4j/Redis/OpenSearch in-cluster via
chart dependencies; `values-prod.yaml` disables those in favor of managed
equivalents (RDS, Neo4j Aura, ElastiCache, AWS OpenSearch) and switches
secrets to an externally-provisioned `Secret` (e.g. via External Secrets
Operator) instead of templating credentials from values.

## Row Level Security

`services/auth`'s `users` table and `services/search`'s
`document_embeddings` table both have Postgres RLS enabled with a
**fail-open** policy: `USING (app_current_tenant() IS NULL OR
organization_id = app_current_tenant())`, where `app_current_tenant()`
reads the `app.tenant_id` session variable (see
`packages/tenancy`). Nothing sets that variable per-request yet, so
`app_current_tenant()` is always `NULL` today and every existing query
sees exactly the rows it always did — this is a scaffold, not enforcement.

To actually enforce tenant isolation, a future change needs to: have
`apps/api-gateway` resolve the caller's tenant (from a JWT claim) and
forward it downstream (it currently forwards no identity headers at
all — see `internal/gateway/proxy.go`), and have each service run `SET
LOCAL app.tenant_id = '<uuid>'` inside the same transaction as its
queries. `packages/tenancy` defines the shared naming for that work
(`TENANT_SESSION_VARIABLE`, `TENANT_ID_HEADER`, `TENANT_ID_CLAIM`) but
does not implement it.

## Secret management & encryption at rest

- **Secrets**: `infra/helm/ai-rxos/templates/secret.yaml` still renders a
  plaintext `Secret` from `values.*.secrets` for dev
  (`externalSecret.enabled=false`). `templates/external-secret.yaml` is a
  new scaffold that renders an [External Secrets
  Operator](https://external-secrets.io) `ExternalSecret` instead when
  `externalSecret.enabled=true` (prod), producing the same secret name/keys
  either way. It assumes ESO and a `SecretStore`/`ClusterSecretStore`
  (`externalSecret.secretStoreRef.name`) already exist in-cluster — this
  chart does not create either.
- **Encryption at rest**: `values.yaml` now exposes an empty
  `storageClass` under `postgresql.primary.persistence`,
  `redis.master.persistence`, and `opensearch.persistence` (and a comment
  on Neo4j's existing `storageClassName`) — point these at an
  encrypted-volume StorageClass for self-hosted/dev clusters. This only
  applies when those subcharts are enabled; `values-prod.yaml` disables
  them entirely in favor of managed AWS services, whose at-rest encryption
  is configured outside this chart.

## Identity migration (BetterAuth adapter)

`services/auth-adapter` is an additive scaffold — see
[`services/auth-adapter/README.md`](services/auth-adapter/README.md) for
what's implemented, what's verified against BetterAuth's actual docs, and
exactly what's still open. `services/auth` is unchanged and still owns
`/api/v1/auth/*`; nothing currently routes to the adapter.

## CI

`.github/workflows/ci.yml` lints/typechecks/builds the JS packages, vets and
builds each Go module, lints and tests each Python service, builds every
Dockerfile, and lints + template-renders the Helm chart.
