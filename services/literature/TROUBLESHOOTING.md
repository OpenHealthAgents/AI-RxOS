# Troubleshooting

This document covers common issues and their resolution for the Literature service.

## Service fails to start

### Symptom

Service container crashes or fails during startup.

### Diagnosis

- Check `DATABASE_URL` and PostgreSQL availability.
- Confirm the `JWT_SECRET` environment variable is present.
- Review container logs for `PostgreSQL pool initialization failed`.

### Fix

- Ensure PostgreSQL is reachable and credentials are correct.
- Set `JWT_SECRET` in the environment.
- Confirm the service can connect to required downstream services.

## `/ready` returns `fail`

### Symptom

Readiness endpoint reports dependency failure.

### Diagnosis

- The readiness endpoint checks:
  - PostgreSQL connectivity
  - Search service health
  - KG service health
  - local orchestrator readiness

### Fix

- Validate `SEARCH_SERVICE_URL` and `KG_SERVICE_URL`.
- Ensure downstream services are healthy and responding with `200`.
- Confirm PostgreSQL is accessible and the connection pool is initialized.

## JWT auth failures

### Symptom

Protected endpoints return `401 Unauthorized`.

### Diagnosis

- Invalid or missing `Authorization` header.
- Token uses wrong signing secret.
- Token payload is malformed.

### Fix

- Send header: `Authorization: Bearer <token>`.
- Use the same `JWT_SECRET` that the service is configured with.
- Ensure token is signed using `HS256`.

## Docker healthcheck fails

### Symptom

Docker reports the container unhealthy.

### Diagnosis

- Healthcheck calls `http://127.0.0.1:8082/health`.
- Service may not have started successfully.

### Fix

- Confirm the service listens on port `8082`.
- Ensure container has started and the app is not offline.
- Check logs for startup errors.

## Metrics endpoint missing values

### Symptom

`/metrics/prometheus` returns no or incomplete metrics.

### Diagnosis

- Prometheus metrics registry may not be initialized properly.
- The service may have failed before registering metrics.

### Fix

- Confirm the application starts without exceptions.
- Ensure `app/observability/metrics.py` is imported via `app/main.py` and route is available.

## Ingestion job failures

### Symptom

Ingestion job status becomes `failed`.

### Diagnosis

- Check `error_message` on the ingestion job record.
- Review dead-letter items for failure details.

### Fix

- Confirm source connector input is valid.
- Validate the query and source values.
- Restart or retry the job using `/api/v1/ingestion/{job_id}/retry`.

## Database schema errors

### Symptom

Queries fail with missing table errors.

### Diagnosis

- Startup schema initialization may have been skipped or failed.

### Fix

- Confirm `services/literature/app/core/lifespan.py` ran during startup.
- Check logs for schema initialization errors.
- Ensure PostgreSQL user has permission to create tables.
