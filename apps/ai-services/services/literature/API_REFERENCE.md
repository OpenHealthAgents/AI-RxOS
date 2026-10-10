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

- Description: Create and enqueue a durable literature ingestion job.
- Security: Bearer JWT required.
- Request body:
  - `source`: one of the source values accepted by `IngestionRequest`
  - `query`: source query expression; PubMed accepts NCBI ESearch expressions,
    including explicit PMID expressions; regulatory jobs require an explicit
    openFDA Drugs@FDA search expression
  - `page_size`: optional integer from 1 to 1000 (default 50, or the
    source-specific configured default); ClinicalTrials and regulatory jobs
    persist the page size alongside their checkpoint
  - `schedule`: optional cron schedule expression
- Response: HTTP 202 and persisted job details including status, progress,
  retry state, dead-letter count, and checkpoint.

For PubMed, the checkpoint records the ESearch page token and completed PMIDs
for that page. The processor preserves query text, source identifiers, and
source metadata while sending normalized articles through KG canonical
reconciliation. Publication date precision remains in the source value;
retrieval and database ingestion times remain separate.

### GET /api/v1/ingestion/{job_id}

- Description: Retrieve ingestion job state.
- Security: Bearer JWT required.
- Response: tenant-scoped job details including the durable checkpoint and
  dead-letter count.

### POST /api/v1/ingestion/{job_id}/trigger

- Description: Trigger a queued ingestion job immediately.
- Security: Bearer JWT required.
- Response: updated ingestion job state.

### POST /api/v1/ingestion/{job_id}/retry

- Description: Retry a failed ingestion job.
- Security: Bearer JWT required.
- Response: updated ingestion job state.
- Retry count is bounded by `INGESTION_MAX_RETRIES`; replay resumes from the
  persisted checkpoint and relies on idempotent PMID/canonical writes.

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
- PubMed malformed records retain their source identifier, diagnostic, status,
  and raw source XML when available.
- ClinicalTrials.gov malformed studies retain their source identifier,
  diagnostic, status, page token, and raw JSON payload. A malformed study is
  dead-lettered without failing other valid studies on the same page.

### ClinicalTrials.gov source behavior

For `source: "clinicaltrials"`, the query is sent to official API v2
`query.id` when it is an NCT ID, otherwise to `query.term`. The API's opaque
`nextPageToken` is durably checkpointed and never interpreted as an offset.
The normalized paper metadata retains registry modules and source precision;
the raw study JSON is stored in the Literature snapshot and referenced by KG
source records. NCT is the canonical namespaced identifier. Do not infer
canonical disease, asset, sponsor-company, or publication links from display
names: source details and reference identifiers are preserved for later
identifier-backed reconciliation.

`CLINICALTRIALS_BASE_URL`, `CLINICALTRIALS_TIMEOUT`,
`CLINICALTRIALS_MAX_RETRIES`, `CLINICALTRIALS_BACKOFF_SECONDS`,
`CLINICALTRIALS_REQUESTS_PER_SECOND`, and `CLINICALTRIALS_PAGE_SIZE` configure
the adapter. Rate pacing is local to a connector instance; it does not
coordinate quota across service replicas.

### FDA Drugs@FDA source behavior

For `source: "regulatory"`, the query is sent as an openFDA search expression
to the official Drugs@FDA API. Each normalized event represents one
application submission, with a stable `FDA:<application>:<submission>` source
identifier. Application/submission payload snapshots are retained in
`literature_source_snapshots`; source record updates do not create a second
event identity. The same durable checkpoint, retry, dead-letter, and tenant
job APIs are used. The source endpoint's total is an application count, so the
job total is finalized from processed and dead-lettered submission events
after successful completion.

The adapter preserves the original submission-status date string rather than
inventing an exact timestamp. It supports bounded retries for rate limits,
transient HTTP errors, and transport/timeouts, with configurable pacing shared
across FDA connector instances in one process (but not across replicas). An
empty query is rejected. If the query exceeds openFDA's 25,000 skip-offset
window, the final accessible page is processed and the job then fails with a
diagnostic so the query can be narrowed. The canonical handoff is KG's
`POST /api/v1/canonical/regulatory-events/ingest`; event history is available
from `/api/v1/canonical/regulatory-events/history` with tenant filtering and
`as_of`. Only a unique exact FDA product-number match links to an asset.


### Google Patents source behavior (Phase 8)

For `source: "patent"`, `query` is required and may be a publication number or
a Google Patents search expression. The adapter uses the public
`/xhr/query` response, follows its page count using an opaque persisted page
index, and normalizes one canonical publication number per result. The
connector stores the complete returned result as a content-hashed source
snapshot and keeps search snippets labeled as excerpts rather than treating
them as full abstracts. Repeated patent publication IDs update one tenant-
scoped Literature row; distinct content hashes retain distinct snapshots.

The Literature processor checkpoints completed publication IDs after each
database/KG handoff and resumes the current source page after worker restart.
Malformed result records are dead-lettered without discarding other records;
HTTP 429, transient 5xx, and transport/timeouts use bounded retries. The KG
handoff is authenticated `POST /api/v1/canonical/ip/patents/ingest`. Applicant,
assignee, inventor, family, and date values remain source-specific facts. A
patent date is never converted into an exact timestamp if the source did not
provide that precision.

Canonical structured licensing/assignment events use
`POST /api/v1/canonical/ip/licensing-events/ingest`; they are not discovered
or extracted automatically. Event parties/assets/patents link only after a
unique exact namespaced identifier match. Exclusivity defaults to `unknown`.
Inspect IP events with
`GET /api/v1/canonical/ip/history?entity_type=patent|patent_family|licensing_event&as_of=...`.
All routes enforce canonical tenant scope, and private events are not written
to global graph/search projections. Google Patents is an aggregator; office
assignment history, automated licensing-source acquisition, legal status
verification, and FTO analysis are not provided. See
`docs/PHASE_8_IMPLEMENTATION.md`.

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
