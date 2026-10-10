# Production Checklist

Use this checklist before promoting the Literature service to production.

## Configuration

- [ ] `JWT_SECRET` is configured in production secrets.
- [ ] `DATABASE_URL` points to the production PostgreSQL instance.
- [ ] `SEARCH_SERVICE_URL`, `KG_SERVICE_URL`, and `LLMWIKI_SERVICE_URL` are set and reachable.
- [ ] `ENVIRONMENT` is set to `production`.
- [ ] `CORS_ALLOWED_ORIGINS` includes trusted frontends.

## Security

- [ ] Do not use default secrets from `app/core/config.py`.
- [ ] Verify bearer token authentication on protected routes.
- [ ] Confirm `Authorization: Bearer <token>` works with the production JWT secret.

## Health and readiness

- [ ] `GET /health` returns `200`.
- [ ] `GET /ready` returns `ready: true`.
- [ ] `GET /metrics/prometheus` returns metrics.
- [ ] Docker healthcheck passes and container is healthy.

## External dependencies

- [ ] PostgreSQL is accessible and schema initialization succeeds.
- [ ] Search service health endpoint returns `200`.
- [ ] KG service health endpoint returns `200`.
- [ ] LLM Wiki service endpoint is reachable.

## Observability

- [ ] Prometheus metrics are scraped successfully.
- [ ] Error and latency metrics are visible.
- [ ] Ingestion metrics appear after job execution.

## Testing

- [ ] `python -m pytest -q` passes.
- [ ] `python -m ruff check app` passes.
- [ ] `python -m ruff format --check app` passes.
- [ ] `python -m mypy app --ignore-missing-imports` passes.

## Deployment

- [ ] Docker image builds successfully.
- [ ] Container starts and exposes port `8082`.
- [ ] Application logs show successful PostgreSQL and orchestrator startup.

## Service behavior

- [ ] Document parsing endpoint handles valid inputs.
- [ ] NLP processing endpoint returns entity and summary payloads.
- [ ] Ingestion jobs can be created, triggered, retried, and cancelled.
- [ ] Dead-letter items are recorded for failed ingestion jobs.
