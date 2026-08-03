# Literature Intelligence Integration Map v2

## Version 2 Summary
This update makes integration contracts explicit, adds event schemas, and resolves ambiguity on search and graph ownership.

## Existing Repository Components Reused
- `services/auth` for authentication, tenant identity, and token validation.
- `services/search` for shared keyword and vector search, plus embedding storage.
- `services/kg` for knowledge graph event consumption, node/edge reconciliation, and graph persistence.
- `apps/api-gateway` for central routing, request validation, and rate limiting.
- `apps/ai-services` for optional LLM-based summarization and extraction.

## Authentication Integration
- Input: `Authorization: Bearer <token>`.
- Validate token using `services/auth` public keys or introspection API.
- Extract claims: `user_id`, `organization_id`, `workspace_id`, `project_id`, `roles`, `permissions`.
- Tenant claims are authoritative and cannot be overridden by client payload.
- The literature service enforces tenant authorization independently of the gateway.

## Search Integration
- `services/search` is the canonical search layer.
- Literature uses search for:
  - keyword search
  - hybrid semantic search
  - embedding upsert/indexing
- Contract:
  - `GET /api/v1/search?q=...&scope=literature&organization_id=...&workspace_id=...`
  - `POST /api/v1/search` with payload `{ query, embedding, filters, tenant }`
  - `POST /api/v1/search/index` with payload `{ document_id, tenant, fields, embedding, chunks }`
- Upsert behavior is idempotent and scoped by `document_id`, `organization_id`, and `workspace_id`.
- If direct upsert is unavailable, literature publishes `document.indexed` events instead of writing directly.
- Ensure the search service enforces tenant scoping on ingested documents.

## Knowledge Graph Integration
- Literature does not write to Neo4j directly.
- Primary integration is event-driven with typed relationship candidate events.
- Event payload contract includes:
  - `event_id`, `event_type`, `version`, `tenant`, `document_id`, `entities`, `relationships`, `evidence`, `created_at`, `trace_id`
- Graph service must handle idempotent event consumption and partial ordering.
- Synchronous graph import is allowed only as fallback and must be clearly documented.
- Tenant metadata is included in event headers and payload.

## Event Transport
- Preferred transport: Kafka with secure authentication, encryption, and ACLs.
- Topics:
  - `literature.document.ingested.v1`
  - `literature.document.processed.v1`
  - `literature.entities.extracted.v1`
  - `literature.relationships.extracted.v1`
  - `literature.document.deduplicated.v1`
  - `literature.document.indexed.v1`
- Events are versioned with `v1` suffixes.
- Payloads omit raw body text unless absolutely needed.
- Security:
  - encrypt events in transit and at rest
  - enforce topic access controls
  - limit sensitive metadata in published events
- Fallback: durable internal queue exposed via `dead_letter` and retry workers.

## External Source Integration
- Support adapters for:
  - PubMed
  - PMC
  - bioRxiv
  - medRxiv
  - patents
  - conference abstracts
  - company reports / websites
- Each adapter implements source-specific throttling, retry, and error handling.
- Fetchers record source health and rate-limit state.
- External source failures do not block unrelated ingestion jobs.

## Gateway and Service Trust Model
- API gateway performs initial request routing and auth validation.
- Literature service performs full validation again, including tenant claims and request integrity.
- The gateway may apply rate limiting and basic protections, but business authorization is enforced within literature.

## Integration Matrix

| Source | Literature Service | Existing Service | Role |
|---|---|---|---|
| Auth | validates token and tenant claims | `services/auth` | Authentication + tenant metadata
| Search | sends query and indexing requests | `services/search` | Keyword + semantic search, embedding storage
| Knowledge Graph | emits candidate events | `services/kg` | Graph ingestion and persistence
| API Gateway | routes and forwards validated requests | `apps/api-gateway` | routing, rate limiting, auth boundary
| LLM / Prompt | requests summarization/extraction | `apps/ai-services` | model orchestration and prompt execution

## Integration Notes
- `services/literature` owns ingestion/extraction state.
- `services/search` owns search index and embedding state.
- `services/kg` owns graph persistence and reconciliation.
- Event payloads include tenant metadata for both search and KG integration.
- Search and KG integrations must support idempotency and retry semantics.

## Blockers and Dependencies Resolved
- Event-driven behavior is explicitly defined, not just planned.
- Search integration is defined with exact endpoint expectations.
- Graph event schema and security expectations are stated.
- Tenant metadata and source-specific rate-limiting requirements are documented.
- NLP library inclusion is acknowledged as an implementation dependency.
