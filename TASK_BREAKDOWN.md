# Literature Intelligence Task Breakdown v2

## Version 2 Summary
This version resolves blocking gaps by adding production tasks for observability, resilience, security, tenant isolation, and explicit integration contracts.

## Delivery Objectives
- Build a production-ready literature ingestion and extraction service.
- Keep auth, search, and graph responsibilities in existing shared services.
- Provide durable, tenant-aware ingestion with manual retry and dead-letter support.
- Ensure search indexing and graph event integration are explicit, secure, and idempotent.
- Add operational runbook, monitoring, and audit requirements.

## Implementation Phases

### Phase 1 — Discovery and Contracts
1. Confirm current repo endpoint and ownership boundaries.
2. Lock down auth/token validation approach and tenant claim propagation.
3. Define exact search and graph integration contracts.
4. Define event transport fallback and schema requirements.

### Phase 2 — Service Structure, Schema, and Deployment
1. Build the literature service folder structure with core, routers, services, integrations, and workers.
2. Define tenant-aware Postgres schema with chunked text storage and audit tables.
3. Add migration helpers and connection pool settings.
4. Add containerization and deployment configuration for Kubernetes / container platform.

### Phase 3 — API and Router Design
1. Extend ingestion endpoints with retry, dead-letter, and operational fields.
2. Add paper metadata, extraction results, and duplicate resolution APIs.
3. Add health and readiness endpoints.
4. Add audit and status endpoints.

### Phase 4 — Ingestion Pipeline Implementation
1. Build source adapters for PubMed, PMC, bioRxiv, medRxiv, patents, conference abstracts, and custom imports.
2. Implement fetcher rate limiting, retry/backoff, and source health metrics.
3. Persist documents and metadata incrementally using chunked storage.
4. Emit ingestion events and record audit entries.

### Phase 5 — Extraction and Deduplication
1. Implement extraction workers with NER, relation extraction, citation extraction, and summarization.
2. Store artifacts in extracted entities, relationships, citations, and document metadata.
3. Support duplicate detection and canonicalization workflows.
4. Emit extraction and deduplication events and update processing status.

### Phase 6 — Search and Indexing Integration
1. Integrate with `services/search` via explicit query and index/upsert contracts.
2. Generate embeddings, if desired, and upsert via search service or events.
3. Use bulk indexing and handle backpressure from search.
4. Emit `document.indexed` events and audit indexing actions.

### Phase 7 — Knowledge Graph Integration
1. Publish versioned relationship candidate events to `services/kg`.
2. Include tenant metadata and evidence in event payloads.
3. Ensure graph service supports idempotent consumption.
4. Only use synchronous KG import as fallback.

### Phase 8 — Security, Tenant Isolation, and Governance
1. Enforce auth validation and tenant isolation on every request.
2. Apply Postgres RLS or tenant filters across all literature tables.
3. Encrypt event transport and service-to-service traffic.
4. Add audit events, retention policies, and data governance controls.

### Phase 9 — Observability and Operations
1. Implement structured logs with `request_id`, `tenant_id`, worker context, and trace IDs.
2. Expose metrics for ingestion, extraction, indexing, retries, and dead-letter counts.
3. Add alerts for backlog growth, failed ingestion rate, search upsert failures, and service dependencies.
4. Create `RUNBOOK.md` with deploy, rollback, incident, and scaling guidance.

## New Components to Build
- `services/literature/app/integrations/external_sources.py`
- `services/literature/app/services/ingestion_service.py`
- `services/literature/app/services/extraction_service.py`
- `services/literature/app/services/indexing_service.py`
- `services/literature/app/services/retry_service.py`
- `services/literature/app/workers/*.py`
- `services/literature/app/models/db_models.py`
- `services/literature/app/models/schemas.py`
- `services/literature/app/models/events.py`
- `services/literature/app/core/events.py`
- `services/literature/app/core/tenant.py`
- `services/literature/app/core/auditing.py`
- `services/literature/RUNBOOK.md`

## Existing Components to Extend
- `services/literature/app/main.py`
- `services/literature/app/core/config.py`
- `services/search` hybrid search and indexing contract
- `services/auth` token and tenant model
- `services/kg` graph ingestion and event schema

## Production Requirements Added
- explicit health/readiness endpoints
- retry and dead-letter workflow endpoints
- chunked document storage for large text
- audit events for operational governance
- tenant-aware indexes and RLS support
- search contract, graph event contract, and fallback queue transport
- runbook for deploy/incident response

## Risks and Assumptions
- `services/literature` is currently a stub and requires full implementation.
- Kafka is not currently implemented in the repo; event transport must support a queue fallback.
- NLP/ML dependencies are missing and must be added before extraction work begins.
- `services/search` owns embedding storage and upsert semantics must be agreed.
- Graph ingestion remains the responsibility of `services/kg`.

## Blocker Resolution Summary
Resolved the previous blockers by:
- defining event topics and payload schema,
- making search upsert contract explicit,
- adding data governance and audit support,
- requiring tenant metadata across all owned tables,
- adding external source retry and dead-letter handling,
- specifying operational health and scaling requirements.

If future implementation hits a blocker, the report should include:
- completed tasks
- pending work
- blocker root cause
- reused existing components
- required dependency or contract
