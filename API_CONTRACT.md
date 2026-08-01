# Literature Intelligence API Contract v2

## Version 2 Summary
This updated contract resolves implementation blockers by specifying production-grade operations, retry semantics, tenant isolation, and integration contract details.

## Existing Literature Service Endpoints
Retain and extend current `services/literature` endpoints:
- `GET /healthz`
- `GET /readyz`
- `GET /api/v1/papers`
- `GET /api/v1/papers/{paper_id}`
- `POST /api/v1/ingestion`
- `GET /api/v1/ingestion/{job_id}`

## API Principles
- All endpoints require `Authorization: Bearer <token>`.
- Auth validation may be local JWT signature verification or auth-service introspection.
- Tenant context is mandatory and derived from auth claims.
- All responses are JSON with standard fields: `code`, `message`, `request_id`, and payload data.
- Use consistent pagination and sorting schemas.
- Expose manual retry and dead-letter inspection for failed ingestion/extraction jobs.

## Ingestion Endpoints

### `POST /api/v1/ingestion`
Create an ingestion job for a source query or document import.

Request body:
- `source` enum: `pubmed`, `biorxiv`, `medrxiv`, `patent`, `conference`, `custom`
- `query` string
- `source_document_id` string, optional for single-document imports
- `source_url` string, optional for explicit fetch
- `workspace_id` UUID, optional (derived from auth if omitted)
- `project_id` UUID, optional (derived from auth if omitted)
- `options` object
  - `fetch_mode` enum: `batch` | `single`
  - `max_documents` int
  - `crawl_depth` int

Response body:
- `id` UUID
- `source`
- `query`
- `status` enum: `queued`, `running`, `completed`, `failed`
- `created_at`
- `started_at` optional
- `completed_at` optional
- `tenant` metadata

### `GET /api/v1/ingestion/{job_id}`
Fetch ingestion job status, progress, and operational details.

Response body includes:
- all fields from job creation
- `document_count`
- `processed_count`
- `failed_count`
- `pending_count`
- `error_message`
- `last_error`
- `backoff_until`
- `dead_letter_count`
- `tenant` metadata

### `POST /api/v1/ingestion/{job_id}/retry`
Retry a failed ingestion job or a specific failed document.

Request body:
- `document_id` optional
- `reason` string

Response body:
- `status`
- `retry_scheduled_at`

### `GET /api/v1/ingestion/{job_id}/dead-letter`
Inspect failed ingestion items.

Response body:
- `items` array of failure records
- `total`

## Paper and Document Endpoints

### `GET /api/v1/papers`
List ingested papers with paging and filters.

Query parameters:
- `page` int
- `page_size` int
- `source` optional
- `status` optional
- `query` optional
- `workspace_id` optional
- `project_id` optional
- `date_from` / `date_to`

Response body:
- `items` array of paper metadata
- `total`
- `page`
- `page_size`

### `GET /api/v1/papers/{paper_id}`
Get full paper metadata, extraction status, and available artifacts.

Response fields:
- `id`, `title`, `authors`, `source`, `doi`, `publication_date`
- `abstract`
- `summary`
- `citation_count`
- `status`
- `document_status`
- `extraction_status`
- `tenant` metadata
- `citations`
- `entities`
- `relationships`
- `text_chunk_count`

## Extraction Result Endpoints

### `GET /api/v1/papers/{paper_id}/entities`
List extracted entities for a paper.

Response fields:
- list of entities with `id`, `type`, `text`, `canonical_id`, `confidence`, `span`, `schema`, `source`, `created_at`
- pagination metadata

### `GET /api/v1/papers/{paper_id}/relationships`
List extracted relationship candidates.

Response fields:
- list of relationship candidates with `id`, `from_entity_id`, `to_entity_id`, `type`, `confidence`, `evidence`, `metadata`, `created_at`

### `GET /api/v1/papers/{paper_id}/citations`
List citation edges extracted from the paper.

Response fields:
- `id`, `cited_source`, `cited_doi`, `confidence`, `created_at`

## Duplicate and Canonicalization Endpoints

### `GET /api/v1/duplicates/{document_id}`
Get duplicate candidates for a document and canonical state.

Response fields:
- `canonical_document_id`
- `duplicate_ids`
- `similarity_score`
- `status`

### `POST /api/v1/duplicates/resolve`
Resolve a duplicate cluster.

Request body:
- `canonical_document_id`
- `duplicate_ids`
- `action` enum: `merge` | `ignore`
- `reason` string

Response fields:
- `status`
- `resolved_at`
- `audit_record_id`

## Search Integration Contract
The literature service uses `services/search` as the canonical search provider.

### Query Search
- `GET /api/v1/search?q=<text>&scope=literature&organization_id=<org>&workspace_id=<ws>`
- Returns keyword search results from the shared search service.

### Hybrid Search
- `POST /api/v1/search`
  Request body:
  - `query` string
  - `embedding` optional array<float>
  - `filters` optional object
  - `tenant` object with `organization_id`, `workspace_id`, `project_id`

### Index Upsert Contract
- Preferred: the search service exposes a document upsert endpoint such as `POST /api/v1/search/index`.
- Upsert payload includes:
  - `document_id`
  - `organization_id`
  - `workspace_id`
  - `source`
  - `title`
  - `abstract`
  - `summary`
  - `content_chunks`
  - `embedding`
  - `metadata`
- Upsert is idempotent and scoped by `document_id` and tenant.
- If direct upsert is not available, literature publishes `document.indexed` events for search ingestion.

## Knowledge Graph Integration Contract
- Primary integration is event-driven.
- Publish versioned events to graph consumer topics.
- Event payloads must include:
  - `event_id`
  - `event_type`
  - `version`
  - `tenant`
  - `document_id`
  - `entities`
  - `relationships`
  - `evidence`
  - `created_at`
- Synchronous graph CRUD direct calls are only allowed as a fallback and must be explicitly documented.

## Audit and Operational Endpoints
### `GET /api/v1/status`
Return dependency status (Postgres, auth, search, broker) and service readiness.

### `GET /api/v1/metrics`
Expose service-level metrics if a metrics endpoint is used directly.

## Common Models

### `PaperSummary`
- `id`
- `title`
- `authors`
- `abstract`
- `summary`
- `source`
- `doi`
- `publication_date`
- `citation_count`
- `status`
- `document_status`
- `extraction_status`
- `tenant`

### `Entity`
- `id`
- `document_id`
- `type`
- `text`
- `canonical_id`
- `confidence`
- `span`
- `schema`
- `source`
- `created_at`

### `RelationshipCandidate`
- `id`
- `document_id`
- `from_entity_id`
- `to_entity_id`
- `type`
- `confidence`
- `evidence`
- `metadata`
- `created_at`

### `ExtractionJobStatus`
- `job_id`
- `document_id`
- `stage`
- `status`
- `started_at`
- `completed_at`
- `error_message`
- `retry_count`
- `dead_letter`

## Auth and Tenant Requirements
- Every endpoint requires `Authorization: Bearer <token>`.
- `organization_id`, `workspace_id`, and `project_id` are derived from auth claims and cannot be overridden with untrusted client input.
- Tenant-aware access is enforced by the service, not just by the gateway.
- Admin-only actions respect existing auth roles.

## Error Handling
- Standard HTTP codes: 400, 401, 403, 404, 409, 429, 500.
- Structured error returns include `code`, `message`, `details`, and `request_id`.
- Transient errors expose retry guidance when appropriate.
- Rate-limit and backpressure conditions return `429` with `Retry-After`.

## Operational Requirements
- Manual retry endpoints for failed ingestion and extraction tasks.
- Dead-letter inspection.
- Support for source-specific rate limit and backoff state.
- Audit traceability of ingestion and duplicate resolution actions.
