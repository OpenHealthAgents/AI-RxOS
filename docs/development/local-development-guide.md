# AI-RxOS Local Development & Operational Standardization Guide

**Document Identifier:** `NZ-DEV-STD-2026-v1.0`  
**Classification:** Engineering Standard Operating Procedure (SOP) & Developer Handbook  
**Authority:** Neozenone AI Principal Architecture Group  
**Target Path:** `/docs/development/local-development-guide.md`  
**Effective Date:** 2026-10-07 | **Status:** RATIFIED & ENFORCED  

---

## 1. Executive Overview & One-Command Quickstart

AI-RxOS / NeoZenome is an enterprise polyglot platform integrating Next.js 14 frontends, high-throughput Go edge services, Python 3.12 FastAPI analytical engines, and four persistent datastores (PostgreSQL + pgvector, Neo4j, Redis, OpenSearch).

To eliminate local configuration friction, local development is fully standardized with automated bootstrap and one-command launch scripts for Windows, Linux, and macOS.

### 1.1 One-Command Startup

For Windows PowerShell:
```powershell
# 1. First-time setup (installs dependencies, generates safe local .env)
pnpm setup

# 2. One-command launch (boots data stores, seeds database, and starts dev servers)
pnpm dev:all
```

For POSIX (Linux / macOS / Git Bash):
```bash
# 1. First-time setup
./scripts/dev-setup.sh

# 2. One-command launch
./scripts/dev-start.sh
```

---

## 2. Prerequisites & Supported Toolchains

| Toolchain | Minimum Version | Recommended Version | Verification Command |
| :--- | :--- | :--- | :--- |
| **Node.js** | `>= 20.0.0` | `v20.x` or `v24.x LTS` | `node -v` |
| **pnpm** | `>= 9.0.0` | `9.15.0+` | `pnpm -v` |
| **Python** | `>= 3.12.0` | `3.12.7+` | `python --version` |
| **Docker** | `>= 24.0.0` | Docker Desktop 4.30+ | `docker compose version` |
| **Go** | `>= 1.22.0` | `1.23+` | `go version` |

---

## 3. Environment Configuration & Secret Governance

### 3.1 Secret Governance Invariant
> [!CAUTION]
> **NEVER COMMIT SECRETS TO GIT.**  
> The `.env` file is strictly ignored in `.gitignore`. All production credentials, real API keys, and corporate certificates must be injected via secret managers (HashiCorp Vault, AWS Secrets Manager, or Kubernetes ExternalSecrets). Any PR containing raw credentials or API keys will trigger immediate automated CI rejection.

### 3.2 Automated Environment Bootstrap
When running `pnpm setup` or `powershell ./scripts/dev-setup.ps1`:
1. `.env.example` is copied to `.env` if `.env` does not exist.
2. Cryptographically secure development tokens are generated locally for:
   - `SEARCH_INTERNAL_TOKEN` (UUIDv4)
   - `JWT_SECRET` (HMAC-SHA256 secret)
   - `EXECUTION_PAYLOAD_KEY` (32-byte Fernet key)
3. Existing `.env` keys are preserved without overwriting customized values.

---

## 4. Comprehensive Environment Variable Dictionary

### 4.1 Global & Platform Runtime
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `NODE_ENV` | `development` | Node.js execution environment (`development`, `production`). | Public |
| `ENVIRONMENT` | `development` | Application lifecycle stage (`development`, `staging`, `production`). | Public |
| `LOG_LEVEL` | `info` | Logging verbosity (`debug`, `info`, `warning`, `error`). | Public |
| `CORS_ALLOWED_ORIGINS`| `http://localhost:3000` | Comma-separated allowed HTTP origins for API Gateway. | Public |

### 4.2 PostgreSQL 16 + pgvector
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `POSTGRES_HOST` | `localhost` / `postgres` | Database hostname (`localhost` for host apps, `postgres` in Docker). | Public |
| `POSTGRES_PORT` | `15432` / `5432` | Host port is `15432` (avoids local Postgres port 5432 conflict). | Public |
| `POSTGRES_DB` | `ai_rxos` | Primary enterprise database name. | Public |
| `POSTGRES_ADMIN_USER` | `ai_rxos` | Superuser/migration owner role. | Sensitive |
| `POSTGRES_ADMIN_PASSWORD` | `changeme` | Migration owner password. | **Secret** |
| `POSTGRES_APP_USER` | `ai_rxos_app` | Least-privilege runtime application user role. | Sensitive |
| `POSTGRES_APP_PASSWORD` | `changeme_app` | Runtime application password. | **Secret** |
| `DATABASE_URL` | `postgresql://ai_rxos_app:changeme_app@localhost:15432/ai_rxos` | Canonical connection URI for application queries. | **Secret** |
| `LITERATURE_MIGRATION_DATABASE_URL` | `postgresql://ai_rxos:changeme@localhost:15432/ai_rxos` | Schema bootstrap URI (admin role). | **Secret** |

### 4.3 Neo4j 5.26 Graph Database
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `NEO4J_URI` | `bolt://localhost:7687` | Bolt protocol connection URI. | Public |
| `NEO4J_USER` | `neo4j` | Neo4j administrative user. | Sensitive |
| `NEO4J_PASSWORD` | `changeme_neo4j` | Neo4j connection password. | **Secret** |

### 4.4 Redis 7 Ephemeral Store & Streams
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `REDIS_HOST` | `localhost` / `redis` | Redis server hostname. | Public |
| `REDIS_PORT` | `6379` | Standard Redis port. | Public |
| `REDIS_URL` | `redis://localhost:6379/0`| Full Redis connection URI. | Sensitive |
| `AGENT_JOB_STREAM` | `agents:jobs` | Redis Stream name for background agent tasks. | Public |
| `AGENT_JOB_GROUP` | `agents-workers` | Redis consumer group name. | Public |
| `AGENT_WORKER_LOCK_TTL_SECONDS` | `390` | Distributed execution lock timeout. | Public |
| `EXECUTION_PAYLOAD_KEY` | *(Auto-generated)* | 32-byte Fernet key for encrypting worker state payloads. | **Secret** |

### 4.5 OpenSearch 2.19 Hybrid Search
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `OPENSEARCH_URL` | `http://localhost:9200` | OpenSearch HTTP cluster endpoint. | Public |
| `OPENSEARCH_USER` | `admin` | Search cluster administrator. | Sensitive |
| `OPENSEARCH_PASSWORD` | `AiRxOS#Search9K` | OpenSearch authentication password. | **Secret** |

### 4.6 Authentication & Edge Security
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `JWT_SECRET` | *(Auto-generated)* | HMAC-SHA256 signature key for access tokens. | **Secret** |
| `JWT_ACCESS_TTL_MINUTES` | `15` | Access token lifespan. | Public |
| `JWT_REFRESH_TTL_DAYS` | `30` | Refresh token lifespan. | Public |
| `SEARCH_INTERNAL_TOKEN` | *(Auto-generated)* | Shared internal service authorization token. | **Secret** |

### 4.7 AI Integrations & Model Registry
| Variable | Default (Dev) | Description | Security |
| :--- | :--- | :--- | :--- |
| `OPENAI_API_KEY` | *(Optional)* | OpenAI API key for `gpt-4o` inference. | **Secret** |
| `ANTHROPIC_API_KEY`| *(Optional)* | Anthropic API key for `claude-3-5-sonnet`. | **Secret** |
| `GEMINI_API_KEY` | *(Optional)* | Google Vertex / Gemini API key. | **Secret** |
| `OLLAMA_BASE_URL` | `http://localhost:11434`| Local Ollama open-source model endpoint. | Public |
| `MODEL_REGISTRY_JSON`| `null` | Optional JSON string overriding default model registry. | Sensitive |

> [!NOTE]
> **Zero External API Cost Guarantee:** The Opportunity Decision Intelligence Engine (`apps/ai-services/app/opportunity_engine`) executes Development Potential Scoring ($DPS$), Bayesian stage transitions, CNS MPO calculation, biomarker patient matching, and historical backtesting **100% locally and deterministically**. No commercial LLM API keys are required for core decision operations.

---

## 5. Development Database Architecture

```mermaid
flowchart LR
    App[AI-RxOS Application Services]
    App -->|Port 15432\nai_rxos_app| PG[(PostgreSQL 16\nCanonical Source-of-Truth)]
    App -->|Port 7687\nneo4j| Neo[(Neo4j 5.26\nGraph Read Projection)]
    App -->|Port 6379| Redis[(Redis 7\nJobs, Streams, Sessions)]
    App -->|Port 9200\nadmin| OS[(OpenSearch 2.19\nHybrid Text & Vectors)]
    PG -.->|Transactional Outbox| Neo
```

### 5.1 Starting the Data Tier Independently
If you want to run application services natively while running databases in Docker:
```powershell
# Start only data stores
pnpm db:up

# Stop data stores
pnpm db:down
```

### 5.2 Database Role Partitioning
To guarantee zero-trust least-privilege security:
- `ai_rxos` (**Admin Role**): Used strictly for schema migrations and DDL operations (`CREATE TABLE`, `ALTER TABLE`).
- `ai_rxos_app` (**Runtime Role**): Granted `SELECT`, `INSERT`, `UPDATE`, `DELETE` on application tables. DDL permissions are denied.

---

## 6. Database Migrations & Seeding Process

### 6.1 Automated Migrations
1. **PostgreSQL Initialization:** `infra/postgres/init.sql` automatically runs on container boot, activating `uuid-ossp` and `vector` extensions.
2. **Runtime Role Setup:** `infra/postgres/bootstrap-runtime-role.sh` creates the `ai_rxos_app` role with locked-down privileges.
3. **Canonical Schema:** Python services execute idempotent migration functions on startup (`services/kg/app/database/canonical_store.py`).
4. **Auth Migrations:** Go auth service runs idempotent SQL migrations (`services/auth/migrations/*.sql`) enforcing RLS policies and audit log hashing.

### 6.2 Seeding Demo Data
To seed canonical ontology entities, synthetic development fixtures, and verify Opportunity benchmark assets:
```powershell
pnpm db:seed
```
This executes:
1. `services/kg/app/seed_demo.py`: Creates 16 canonical demo entities (`ERBB2`, `ESR1`, `TROP2`, etc.).
2. Verification of the 4 real-world oncology benchmark assets (`Zongertinib`, `Neratinib`, `Tucatinib`, `Poziotinib`).

---

## 7. Background Workers & Queue Management

The platform utilizes Redis Streams for reliable, distributed background processing.

### 7.1 Running the Worker Locally
To run the background task worker natively in Python:
```powershell
# From services/agents directory
cd services/agents
python -m app.jobs.worker
```

### 7.2 Inspecting Redis Streams
Using `redis-cli`:
```bash
# Connect to local Redis
redis-cli -p 6379

# Check job stream length
XLEN agents:jobs

# Inspect pending worker tasks
XPENDING agents:jobs agents-workers

# Check Dead Letter Queue
XLEN agents:jobs:dead-letter
```

---

## 8. Test Environment & Quality Gates

The test harness enforces full validation across all languages:

```mermaid
flowchart TD
    T[Test Verification Suite]
    T --> TS["TypeScript / Web\npnpm typecheck && pnpm test"]
    T --> PY["Python\npytest apps/ai-services/tests (228 tests)"]
    T --> GO["Go\ngo test ./... in gateway, auth, search"]
```

### 8.1 Running All Tests
```powershell
pnpm test:all
```

### 8.2 Targeted Subsystem Tests
```powershell
# TypeScript Typecheck
pnpm typecheck

# Opportunity Decision Intelligence Engine (FastAPI)
cd apps/ai-services
pytest tests -q

# Go Services
cd apps/api-gateway && go test ./...
cd services/auth && go test ./...
cd services/search && go test ./...
```

---

## 9. Observability & Monitoring

### 9.1 OpenTelemetry Distributed Tracing
All microservices propagate W3C Trace Context headers (`traceparent`, `X-Request-Id`).
- Trace Exporter: OTLP HTTP/gRPC exporter (`OTEL_EXPORTER_OTLP_ENDPOINT`).
- Local Jaeger UI: `http://localhost:16686` (when Jaeger profile is enabled).

### 9.2 Prometheus Metrics
Every service exposes an unauthenticated `/metrics` endpoint:
- API Gateway: `http://localhost:8080/metrics`
- Auth Service: `http://localhost:8081/metrics`
- Opportunity Engine: `http://localhost:8090/metrics`
- Knowledge Graph: `http://localhost:8083/metrics`

### 9.3 Structured JSON Logs
All Python and Go services output single-line JSON logs with automatic in-flight redaction of secrets, auth tokens, and sensitive biological sequences.

---

## 10. Comprehensive API Documentation Catalog

When services are running locally, interactive OpenAPI / Swagger UI documentation is available at:

| Service | Host Port | Interactive Documentation URL | Primary Domain |
| :--- | :--- | :--- | :--- |
| **API Gateway** | `8080` | `http://localhost:8080/healthz` | Edge routing & reverse proxy |
| **Opportunity Decision Engine** | `8090` | [http://localhost:8090/docs](http://localhost:8090/docs) | 14 Decision, Biology & Backtest Engines |
| **Canonical Knowledge Graph** | `8083` | [http://localhost:8083/docs](http://localhost:8083/docs) | Canonical entities, claims & outbox |
| **Literature Intelligence** | `8082` | [http://localhost:8082/docs](http://localhost:8082/docs) | PubMed, CT.gov, FDA, Patent Ingestion |
| **Search Gateway** | `8084` | [http://localhost:8084/healthz](http://localhost:8084/healthz) | OpenSearch & LLM-Wiki Hybrid Search |
| **Agent Orchestrator** | `8085` | [http://localhost:8085/docs](http://localhost:8085/docs) | LangGraph agent harness & tool registry |
| **Scientific Workflows** | `8086` | [http://localhost:8086/docs](http://localhost:8086/docs) | Multi-step scientific workflow coordinator |
| **Report Generation** | `8087` | [http://localhost:8087/docs](http://localhost:8087/docs) | Automated Markdown dossiers |
| **Molecular Docking** | `8088` | [http://localhost:8088/docs](http://localhost:8088/docs) | Biophysical docking & scoring |
| **Knowledge BFF** | `8091` | [http://localhost:8091/docs](http://localhost:8091/docs) | Read-optimized Neo4j graph facades |
| **LLM-Wiki** | `8092` | [http://localhost:8092/docs](http://localhost:8092/docs) | Persistent markdown wiki & embeddings |
| **Decision Workspace (Web)** | `3000` | [http://localhost:3000](http://localhost:3000) | NeoZenome End-User Workspace |
| **Admin Console** | `3001` | [http://localhost:3001](http://localhost:3001) | Administrative oversight portal |

---

## 11. Development Scripts Reference

| Script | Platform | Command | Purpose |
| :--- | :--- | :--- | :--- |
| `dev-setup.ps1` | Windows | `powershell ./scripts/dev-setup.ps1` | Checks toolchains, bootstraps `.env`, installs pnpm deps |
| `dev-setup.sh` | POSIX | `./scripts/dev-setup.sh` | Bash equivalent for Linux/macOS setup |
| `dev-start.ps1` | Windows | `powershell ./scripts/dev-start.ps1 -Mode hybrid` | One-command startup (datastores + seed + frontend) |
| `dev-start.sh` | POSIX | `./scripts/dev-start.sh hybrid` | POSIX one-command startup |
| `seed-db.ps1` | Windows | `powershell ./scripts/seed-db.ps1` | Idempotent canonical entity and benchmark fixture seeding |
| `run-tests.ps1` | Windows | `powershell ./scripts/run-tests.ps1` | Cross-service test runner (TypeScript, Python, Go) |

---

*Authored by Neozenone AI Principal Architecture Group.*  
*AI-RxOS: Grounded in Evidence, Built for Decisions.*
