# API Reference

This file documents the Literature service API surface.

## Health and Observability

### GET /healthz

- Description: Basic liveness check.
- Response: `200`
- Body: `{ "status": "ok", "service": "literature" }`

### GET /health

- Description: API health endpoint.
- Response: `200`
- Body: `{ "status": "ok", "service": "literature" }`

### GET /live

- Description: Liveness indicator.
- Response: `200`
- Body: `{ "status": "ok", "service": "literature", "live": true }`

### GET /ready

- Description: Readiness check; validates PostgreSQL, Search service, KG service, and orchestrator readiness.
- Response: `200`
- Body:
  - `status`: `ok` or `fail`
  - `ready`: boolean
  - `dependencies`: dependency status details
  - `metrics`: uptime, parser, and orchestrator metrics

### GET /metrics

- Description: JSON metrics payload.
- Response: `200`
- Body: service-level metrics and uptime.

### GET /metrics/prometheus

- Description: Prometheus exposition format.
- Response: `200`
- Content-Type: `text/plain`

### GET /api/v1/health

- Description: Versioned health endpoint.
- Response: `200`
- Body: `{ "status": "ok", "service": "literature" }`

## Document APIs

### POST /api/v1/documents/parse

- Description: Parse document content and extract structured metadata.
- Security: Bearer JWT required.
- Request body:
  - `format`: `pdf`, `xml`, `html`, `nxml`, or `jats`
  - `content`: document content as string
- Response body:
  - `metadata`: parsed `DocumentMetadata`
  - `duplicate`: boolean
  - `metrics`: parser metric snapshot
- Error codes:
  - `400` invalid content or parse failure
  - `409` duplicate document detected

## NLP APIs

### POST /api/v1/nlp/process

- Description: Process parsed document metadata through the biomedical NLP pipeline.
- Security: Bearer JWT required.
- Request body: `DocumentMetadata` JSON structure.
- Response body:
  - `document_id`
  - `sentences`
  - `tokens`
  - `detected_entities`
  - `entities`
  - `relationships`
  - `summary`
  - `processing_metadata`
  - `execution_metrics`
- Error codes:
  - `400` invalid document metadata or pipeline error

## Ingestion APIs

### POST /api/v1/ingestion

- Description: Create and enqueue a literature ingestion job.
- Security: Bearer JWT required.
- Request body:
  - `source`: `pubmed`, `biorxiv`, `medrxiv`, `patent`, or `conference`
  - `query`: search or ingestion query string
  - `schedule`: optional cron schedule expression
- Response: persisted ingestion job details.

### GET /api/v1/ingestion/{job_id}

- Description: Retrieve ingestion job state.
- Security: Bearer JWT required.
- Response: ingestion job details.

### POST /api/v1/ingestion/{job_id}/trigger

- Description: Trigger a queued ingestion job immediately.
- Security: Bearer JWT required.
- Response: updated ingestion job state.

### POST /api/v1/ingestion/{job_id}/retry

- Description: Retry a failed ingestion job.
- Security: Bearer JWT required.
- Response: updated ingestion job state.

### POST /api/v1/ingestion/{job_id}/cancel

- Description: Cancel an ingestion job.
- Security: Bearer JWT required.
- Response: updated ingestion job state.

### GET /api/v1/ingestion/{job_id}/dead-letter

- Description: Retrieve dead-letter items associated with a job.
- Security: Bearer JWT required.
- Response body:
  - `items`: array of dead-letter records
  - `total`: count

## Paper APIs

### GET /api/v1/papers

- Description: List ingested papers.
- Security: Bearer JWT required.
- Query parameters:
  - `page`: page number (default 1)
  - `page_size`: page size (default 20, max 100)
- Response body:
  - `items`: list of paper summaries
  - `total`: total count
  - `page`: current page
  - `pageSize`: page size

### GET /api/v1/papers/{paper_id}

- Description: Retrieve metadata for a single paper.
- Security: Bearer JWT required.
- Response body: `Paper` metadata.
- Error codes:
  - `404` paper not found

## Security

Protected endpoints require `Authorization: Bearer <token>`.
Tokens are validated using the `JWT_SECRET` setting and HS256.
