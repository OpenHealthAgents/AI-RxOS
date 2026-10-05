# Environment Configuration

This document describes environment variables used by the Literature service.

## Required production variables

- `LITERATURE_DATABASE_URL` — restricted runtime PostgreSQL connection string. It must use a non-superuser, non-BYPASSRLS role with DML grants on Literature tables.
- `LITERATURE_MIGRATION_DATABASE_URL` — schema-owner connection used only by startup `ensure_schema`; do not use it for application reads/writes.
- `JWT_SECRET` — JWT signing secret for bearer authentication.
- `SEARCH_SERVICE_URL` — base URL for downstream Search service.
- `KG_SERVICE_URL` — base URL for downstream Knowledge Graph service.
- `LLMWIKI_SERVICE_URL` — base URL for downstream LLM Wiki service.

## Optional and default variables

These defaults are defined in `app/core/config.py` and are suitable for local development only.

- `ENVIRONMENT` — defaults to `development`
- `LOG_LEVEL` — defaults to `info`
- `REDIS_URL` — defaults to `redis://redis:6379/0`
- `NEO4J_URI` — defaults to `bolt://neo4j:7687`
- `NEO4J_USER` — defaults to `neo4j`
- `NEO4J_PASSWORD` — defaults to `changeme_neo4j`
- `OPENSEARCH_URL` — defaults to `http://opensearch:9200`
- `SEARCH_SERVICE_TIMEOUT_SECONDS` — defaults to `5`
- `SEARCH_SERVICE_MAX_RETRIES` — defaults to `3`
- `KG_SERVICE_TIMEOUT_SECONDS` — defaults to `5`
- `KG_SERVICE_MAX_RETRIES` — defaults to `3`
- `LLMWIKI_SERVICE_TIMEOUT_SECONDS` — defaults to `5`
- `LLMWIKI_SERVICE_MAX_RETRIES` — defaults to `3`
- `PUBMED_BASE_URL` — defaults to the NCBI E-utilities base URL
- `PUBMED_API_KEY` — optional NCBI API key; not logged or persisted.
- `PUBMED_EMAIL` — optional contact email sent with E-utilities requests.
- `PUBMED_REQUESTS_PER_SECOND` — defaults to 3, shared-process request pacing.
- `PUBMED_MAX_RETRIES` — defaults to 3 bounded retries for NCBI HTTP failures.
- `PUBMED_BACKOFF_SECONDS` — defaults to 0.5 seconds before exponential retry backoff.
- `INGESTION_MAX_RETRIES` — defaults to 5 manual job retries.
- `PMC_BASE_URL` — defaults to the NCBI PMC API base URL
- `CLINICALTRIALS_BASE_URL` — defaults to `https://clinicaltrials.gov/api/v2/studies`
- `CLINICALTRIALS_TIMEOUT` — defaults to 10 seconds per API request.
- `CLINICALTRIALS_MAX_RETRIES` — defaults to 3 bounded retries for 429, transient 5xx, and transport errors; permanent 4xx responses are not retried.
- `CLINICALTRIALS_BACKOFF_SECONDS` — defaults to 0.5 seconds before exponential retry backoff.
- `CLINICALTRIALS_REQUESTS_PER_SECOND` — defaults to 2 requests per second per connector instance. This is process-local pacing, not a distributed quota coordinator.
- `CLINICALTRIALS_PAGE_SIZE` — defaults to 50 API v2 studies per page; accepted job override is 1–1000.
- `FDA_REGULATORY_BASE_URL` — defaults to the official openFDA Drugs@FDA endpoint.
- `FDA_REGULATORY_TIMEOUT` — defaults to 10 seconds per request.
- `FDA_REGULATORY_MAX_RETRIES` — defaults to 3 bounded retries for 429, transient 5xx, and transport failures; permanent 4xx responses are not retried.
- `FDA_REGULATORY_BACKOFF_SECONDS` — defaults to 0.5 seconds before exponential retry backoff.
- `FDA_REGULATORY_REQUESTS_PER_SECOND` — defaults to one request per second, shared across FDA connector instances in a process; it is not a distributed quota coordinator.
- `FDA_REGULATORY_PAGE_SIZE` — defaults to 50 application records per page; an ingestion job may override it with a size from 1 to 1000.
- `GOOGLE_PATENTS_BASE_URL` — defaults to `https://patents.google.com`.
- `GOOGLE_PATENTS_TIMEOUT` — defaults to 15 seconds per request.
- `GOOGLE_PATENTS_MAX_RETRIES` — defaults to 3 bounded retries for HTTP 429, transient 5xx, and transport errors; other 4xx responses are not retried.
- `GOOGLE_PATENTS_BACKOFF_SECONDS` — defaults to 0.5 seconds before exponential retry backoff.
- `GOOGLE_PATENTS_REQUESTS_PER_SECOND` — defaults to 0.5 requests/second, shared process-wide among Google Patents connector instances. It does not coordinate quotas across replicas.
- `GOOGLE_PATENTS_PAGE_SIZE` — defaults to 20 results per source page; accepted job override is 1–100.
- `BIORXIV_BASE_URL` — defaults to bioRxiv API endpoint
- `MEDRXIV_BASE_URL` — defaults to medRxiv API endpoint
- `CORS_ALLOWED_ORIGINS` — defaults to `http://localhost:3000`

## Notes

- `JWT_SECRET` must be unique and kept confidential in production.
- Runtime `LITERATURE_DATABASE_URL` must not be a superuser or have `BYPASSRLS`; schema DDL runs through `LITERATURE_MIGRATION_DATABASE_URL` only.
- Compose provisions the shared `ai_rxos_app` role in `infra/postgres/bootstrap-runtime-role.sh`. Self-hosted Helm provisions it at first PostgreSQL initialization. Managed PostgreSQL deployments must provision the role/grants out of band and provide both URLs through their secret manager.
- `SEARCH_SERVICE_URL`, `KG_SERVICE_URL`, and `LLMWIKI_SERVICE_URL` must be reachable by the deployed container.
- `ENVIRONMENT` may be set to `test` during CI to bypass real database startup in startup lifespan.
- ClinicalTrials.gov page tokens are persisted opaquely in durable job checkpoints. ClinicalTrials API tests use mocked responses; a live smoke test is separate and may be unavailable in restricted network environments.
- FDA regulatory jobs require the PostgreSQL-backed durable job path and an explicit openFDA search expression. openFDA pagination has a 25,000 offset ceiling; broad queries beyond the accessible window fail after processing the last accessible page and must be narrowed. Mocked adapter tests do not depend on live FDA availability.
- Patent jobs require the PostgreSQL-backed durable job path and an explicit identifier or query. The public Google Patents endpoint can throttle or change its response format; production acquisition remains limited to that aggregator and does not validate legal ownership or licensing conclusions.
