# Deployment Guide

This document describes how to deploy the Literature service in production.

## Container deployment

Build the Docker image from the repository root:

```bash
docker build -t ai-rxos-literature -f services/literature/Dockerfile services/literature
```

Run the container:

```bash
docker run -p 8082:8082 \
  -e DATABASE_URL="postgresql://user:password@postgres:5432/ai_rxos" \
  -e JWT_SECRET="<secure-secret>" \
  -e SEARCH_SERVICE_URL="http://search:8084" \
  -e KG_SERVICE_URL="http://kg:8083" \
  -e LLMWIKI_SERVICE_URL="http://llmwiki:8086" \
  ai-rxos-literature
```

The container exposes port `8082` and includes a healthcheck on `/health`.

## Environment requirements

- PostgreSQL instance accessible via `DATABASE_URL`
- Search service at `SEARCH_SERVICE_URL`
- KG service at `KG_SERVICE_URL`
- LLM Wiki service at `LLMWIKI_SERVICE_URL`
- JWT secret set in `JWT_SECRET`

## Startup behavior

On startup, the service:

- initializes an asyncpg PostgreSQL connection pool
- ensures the `literature_papers` and `literature_ingestion_jobs` tables exist
- starts the ingestion orchestrator worker and scheduler

If startup fails to connect to PostgreSQL, the service continues in degraded mode but marks readiness accordingly.

## Health checks

The Docker healthcheck uses `/health` and expects a `200` status.

For production orchestration, use `/ready` to verify dependency readiness.

## Runtime ports

- Application API: `8082`
- Health and metrics: `8082`

## Authentication

All protected endpoints require `Authorization: Bearer <token>` with a JWT signed using `JWT_SECRET`.

## Production best practices

- Do not use default secret values from `app/core/config.py` in production.
- Use secure secrets for `JWT_SECRET` and service credentials.
- Ensure dependent services are reachable and have their own health checks.
- Monitor `/metrics/prometheus` for end-to-end production telemetry.
