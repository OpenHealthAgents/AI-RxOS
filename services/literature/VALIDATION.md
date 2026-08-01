# Validation Guide

This document describes the validation checks for the Literature service.

## Service validation

Validate the service by confirming:

- `GET /healthz`, `GET /health`, and `GET /live` return `200` and correct status payloads.
- `GET /ready` returns `ready: true` when dependencies are healthy.
- `GET /metrics/prometheus` returns Prometheus plaintext metrics.
- Authenticated calls to protected endpoints return `200` for valid JWTs and `401` for invalid or missing tokens.

## Data validation

- `POST /api/v1/documents/parse` must accept valid document content and return metadata.
- Duplicate documents raise `409` and return a duplicate error.
- `POST /api/v1/nlp/process` must accept parsed document metadata and return NLP results.
- Ingestion endpoints must persist job state and correctly transition through queued, running, completed, failed, and cancelled statuses.

## Static validation

Perform code quality checks before production deployment:

```bash
python -m ruff check app
python -m ruff format --check app
python -m mypy app --ignore-missing-imports
```

## Runtime validation

1. Start the service.
2. Confirm `/health` and `/ready` endpoints return expected values.
3. Verify that the database schema is created successfully by the startup lifespan handler.
4. Confirm scheduler and orchestrator metrics are present in `/metrics`.
5. Validate failure modes by:
   - stopping a downstream service
   - verifying readiness changes to `fail`
   - confirming error metrics increment

## Dependency validation

The readiness endpoint checks:

- PostgreSQL connection availability
- Search service health via `search_service_url`
- KG service health via `kg_service_url`
- local orchestrator readiness

Ensure these dependencies are reachable in the target environment.
