# Environment Configuration

This document describes environment variables used by the Literature service.

## Required production variables

- `DATABASE_URL` — PostgreSQL connection string.
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
- `PUBMED_BASE_URL` — defaults to the NCBI PubMed API base URL
- `PMC_BASE_URL` — defaults to the NCBI PMC API base URL
- `CLINICALTRIALS_BASE_URL` — defaults to ClinicalTrials.gov API endpoint
- `BIORXIV_BASE_URL` — defaults to bioRxiv API endpoint
- `MEDRXIV_BASE_URL` — defaults to medRxiv API endpoint
- `CORS_ALLOWED_ORIGINS` — defaults to `http://localhost:3000`

## Notes

- `JWT_SECRET` must be unique and kept confidential in production.
- `DATABASE_URL` must point to a PostgreSQL instance with the `ai_rxos` schema or sufficient privileges to create it.
- `SEARCH_SERVICE_URL`, `KG_SERVICE_URL`, and `LLMWIKI_SERVICE_URL` must be reachable by the deployed container.
- `ENVIRONMENT` may be set to `test` during CI to bypass real database startup in startup lifespan.
