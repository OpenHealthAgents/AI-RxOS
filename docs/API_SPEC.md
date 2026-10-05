# AI-RxOS API Baseline

## Current API Layers

- `apps/api-gateway`: Go gateway, JWT validation, rate limiting, and proxy.
- `services/auth`: identity and authentication APIs.
- `services/literature`: ingestion, paper, extraction, and health contracts.
- `services/kg`: graph CRUD/import/version/evidence APIs.
- `services/search`: hybrid search and indexing contracts.
- `services/agents`: authenticated task, streaming, prompt, tool, model,
  memory, and conversation APIs.
- `services/llm-wiki`: durable page/version/provenance APIs.

Detailed contracts remain in `API_CONTRACT.md`, service READMEs, and source
routers. They are implementation contracts only where matching code and tests
exist.

## Contract Rules

- Requests and responses are versioned at service boundaries.
- Correlation/request IDs propagate where the service supports them.
- Authentication and tenant context are mandatory for user-facing APIs.
- Services validate tenant scope themselves; gateway validation alone is not
  sufficient.
- Evidence APIs expose provenance, confidence, temporal context, and source
  identifiers.
- Errors are structured and do not expose secrets or stack traces.

## Current Gaps

- Gateway tenant headers are not consistently propagated downstream.
- Some internal service routers are not independently authenticated.
- Search query paths do not uniformly apply tenant filters.
- Older Literature sources still include legacy/in-memory paths. PubMed,
  ClinicalTrials.gov, and FDA Drugs@FDA now use durable PostgreSQL jobs,
  source snapshots, and canonical evidence integration.
- `apps/ai-services` is an in-memory facade/stub; `services/agents` is the
  substantive runtime.
- Kafka/event contracts are documented, but a complete durable broker path is
  not present.

## Canonical Data API (Phase 2, `services/kg`)

All routes below are implemented by the existing KG FastAPI service. The Go
gateway forwards `/api/v1/canonical` to KG. Requests require a Bearer JWT;
canonical scope is derived from its verified `sub` and `organizationId` /
`organization_id` claims. No request-body organization scope is accepted.

| Method | Path | Behavior |
| --- | --- | --- |
| GET/POST | `/api/v1/canonical/entities?entity_type=...` | Paginated entity listing / create with source provenance, identifiers, and aliases. |
| GET | `/api/v1/canonical/entities/{entity_id}` | Entity detail with namespaced IDs and aliases. |
| GET/POST | `/api/v1/canonical/assets` | Therapeutic asset collection, including modality validation. |
| GET | `/api/v1/canonical/assets/{entity_id}` | Asset detail. |
| GET/POST | `/api/v1/canonical/targets` | Target collection. |
| GET/POST | `/api/v1/canonical/diseases` | Disease collection. |
| GET/POST | `/api/v1/canonical/indications` | Indication collection. |
| GET/POST | `/api/v1/canonical/biomarkers` | Biomarker collection; genomic and non-genomic types supported. |
| GET/POST | `/api/v1/canonical/companies` | Company collection. |
| GET/POST | `/api/v1/canonical/trials` | Trial collection. |
| GET/POST | `/api/v1/canonical/publications` | Publication collection; literature identifiers are namespaced. |
| GET/POST | `/api/v1/canonical/patents` | Patent entity collection; stores source observations, not legal conclusions. |
| GET/POST | `/api/v1/canonical/regulatory-events` | Regulatory event collection. |
| GET/POST | `/api/v1/canonical/mechanisms` | Mechanism collection. |
| GET/POST | `/api/v1/canonical/combinations` | Combination collection. |
| GET/POST | `/api/v1/canonical/resistance-mechanisms` | Resistance mechanism collection. |
| GET | `/api/v1/canonical/resolve?namespace=...&identifier_type=...&value=...` | Exact identifier resolution; unreviewed alias candidates remain unresolved. |
| GET | `/api/v1/canonical/resolve-name?entity_type=...&q=...` | Exact normalized-name lookup; multiple candidates return `ambiguous`. |
| POST | `/api/v1/canonical/relationships` | Create a typed predicate relationship with required source-backed observation. |
| GET | `/api/v1/canonical/relationships?entity_id=...` | Paginated relationships visible to caller. |
| POST | `/api/v1/canonical/observations` | Append a source-linked, time-aware observation. |
| GET | `/api/v1/canonical/entities/{entity_id}/observations` | Paginated observations with source and review metadata. |
| POST | `/api/v1/canonical/claims` | Create a source-backed claim with provenance, confidence, valid-time bounds, and optional observation linkage. |
| POST | `/api/v1/canonical/claims/{claim_id}/evidence` | Attach supporting, contradicting, context, or derived evidence to a claim. |
| GET | `/api/v1/canonical/entities/{entity_id}/claims?as_of=<RFC3339>` | List claims valid and available to AI-RxOS at the timezone-aware cutoff; omitting `as_of` uses current database transaction time. |
| GET | `/api/v1/canonical/claims/{claim_id}/lineage?as_of=<RFC3339>` | Retrieve the claim and only evidence available and valid at the same knowledge-state cutoff, with nested observation/source provenance. |

Temporal intervals use inclusive bounds (`valid_from <= as_of <= valid_to`);
null bounds are unbounded. The historical APIs require timezone-aware
timestamps. Publication/event time is retained as provenance and is not
substituted for ingestion/availability time.

Errors use HTTP 401 (missing/invalid token), 403 (scope/reviewer/operator
policy), 404 (not found or out-of-scope), 409 (duplicate namespaced ID), 422
(validation), and 503 when the canonical store is unavailable. Private entities
are not included in global projections. These canonical contracts do not make
the pre-existing `/api/v1/graph` or Search routes tenant-safe.

## Literature PubMed ingestion (Phase 5)

The existing Literature API controls PubMed acquisition; no duplicate KG
ingestion API is introduced:

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/v1/ingestion` | Create a tenant-scoped PubMed job using an existing NCBI query expression. |
| GET | `/api/v1/ingestion/{job_id}` | Inspect durable status, progress, checkpoint, and retry state within tenant scope. |
| POST | `/api/v1/ingestion/{job_id}/retry` | Replay a failed job from its persisted checkpoint, subject to the bounded retry limit. |
| POST | `/api/v1/ingestion/{job_id}/cancel` | Request cancellation through the existing job controller. |
| GET | `/api/v1/ingestion/{job_id}/dead-letter` | Inspect malformed-record and job-level failures within tenant scope. |
| GET | `/api/v1/papers` / `/api/v1/papers/{paper_id}` | Inspect normalized Literature papers, PubMed identifiers, source metadata, retrieval/ingestion times, and canonical reconciliation status. |

The Literature processor calls KG's authenticated
`POST /api/v1/canonical/pubmed/ingest` internal endpoint. That endpoint routes
the article through canonical identifier reconciliation, observations, a
source-fact claim, supporting evidence, and the existing projection outbox.
PubMed query text and progress/checkpoint state remain on the Literature job.
`PUBMED_API_KEY`, `PUBMED_EMAIL`, `PUBMED_REQUESTS_PER_SECOND`,
`PUBMED_MAX_RETRIES`, and `PUBMED_BACKOFF_SECONDS` configure NCBI access. See
`services/literature/API_REFERENCE.md` and
`PHASE_5_IMPLEMENTATION.md` for payload and recovery details.

## ClinicalTrials.gov ingestion (Phase 6)

The same Literature job APIs support `source: "clinicaltrials"`; there is no
parallel trial-ingestion API:

| Method | Path | Behavior |
| --- | --- | --- |
| POST | `/api/v1/ingestion` | Create a tenant-scoped ClinicalTrials.gov API v2 query job. An NCT ID is accepted as a deterministic query; other expressions use the existing source query field. |
| GET | `/api/v1/ingestion/{job_id}` | Inspect the durable trial job, progress, retry state, page-token checkpoint, and dead-letter count. |
| POST | `/api/v1/ingestion/{job_id}/retry` | Retry a failed job from its persisted page-token/record checkpoint, subject to the existing bounded job retry policy. |
| GET | `/api/v1/ingestion/{job_id}/dead-letter` | Inspect malformed source records and job failures within tenant scope. |
| GET | `/api/v1/papers` / `/api/v1/papers/{paper_id}` | Inspect the normalized trial record, NCT identity, retained source metadata, raw-snapshot reference, and canonical reconciliation status. |

The job accepts an optional `page_size` (1–1000; default from
`CLINICALTRIALS_PAGE_SIZE`). The Literature processor calls KG's authenticated
`POST /api/v1/canonical/clinicaltrials/ingest` internal endpoint. KG reconciles
the namespaced NCT identifier, persists source-linked facts as observations,
source-fact claims and supporting evidence, and updates the transactional
projection outbox when current canonical trial attributes change.
ClinicalTrials.gov v2 page tokens are treated as opaque values. Network retry,
timeout, backoff, request pacing, and page size are controlled by
`CLINICALTRIALS_TIMEOUT`, `CLINICALTRIALS_MAX_RETRIES`,
`CLINICALTRIALS_BACKOFF_SECONDS`, `CLINICALTRIALS_REQUESTS_PER_SECOND`, and
`CLINICALTRIALS_PAGE_SIZE`. See `PHASE_6_IMPLEMENTATION.md` and
`services/literature/ENVIRONMENT.md` for limits and recovery details.

## FDA regulatory ingestion (Phase 7)

Regulatory source acquisition uses the same tenant-scoped Literature job and
inspection APIs with `source: "regulatory"`; no parallel regulatory job API
is introduced. The `query` must be an explicit openFDA Drugs@FDA search
expression (for example, `application_number:NDA021248`). The optional
`page_size` is persisted in the job checkpoint and bounded to 1–1000. When
PostgreSQL-backed durable jobs are unavailable, this source fails with HTTP
503 rather than falling back to the legacy in-memory ingestion path.

The Literature processor persists FDA application/submission snapshots and
hands normalized submission events to KG's authenticated
`POST /api/v1/canonical/regulatory-events/ingest`. Canonical history is
available at `GET /api/v1/canonical/regulatory-events/history` with event,
regulator, jurisdiction, type, status, pagination, and timezone-aware
`as_of` filters. Exact FDA product-number identifiers may link an event to a
unique therapeutic asset; name-only links are not inferred. FDA submission
status dates remain source strings (for example, `20240115`) and are not
converted to event instants.

`FDA_REGULATORY_BASE_URL`, `FDA_REGULATORY_TIMEOUT`,
`FDA_REGULATORY_MAX_RETRIES`, `FDA_REGULATORY_BACKOFF_SECONDS`,
`FDA_REGULATORY_REQUESTS_PER_SECOND`, and `FDA_REGULATORY_PAGE_SIZE`
configure source access. Request pacing is shared among connector instances
in a process, but not coordinated across replicas. The source API's total count is per application,
while ingestion records are flattened submission events; job totals are
finalized from processed and dead-lettered events on successful completion.
Queries beyond openFDA's 25,000 offset window are stopped explicitly after
the final accessible page, and should be narrowed. See
`PHASE_7_IMPLEMENTATION.md` and `services/literature/ENVIRONMENT.md`.

## Patent and licensing intelligence (Phase 8)

Patent acquisition uses the existing durable Literature job APIs with
`source: "patent"` and a required patent identifier or Google Patents query.
The source adapter uses Google Patents' public search response, bounded retries,
and process-local request pacing. It stores the content-hashed source response
in `literature_source_snapshots`; current patent rows are tenant-scoped and
idempotent by publication number and tenant. Patent source-date values remain
strings at the precision supplied by Google Patents.

KG exposes authenticated `POST /api/v1/canonical/ip/patents/ingest` and
`POST /api/v1/canonical/ip/licensing-events/ingest`. It also exposes
`GET/POST /api/v1/canonical/patent-families` and
`GET/POST /api/v1/canonical/licensing-events`, plus
`GET /api/v1/canonical/ip/history?entity_type=...&source_identifier=...&as_of=...`.
Patent identity uses jurisdiction-scoped publication/application/grant
identifiers when supplied; family identity is separately namespaced. History
uses the canonical Phase 4 knowledge-state cutoff and returns the source facts,
claims, and source-record references available at that cutoff.

Licensing and assignment announcements enter through the typed canonical
licensing-event endpoint with source URL, hash/reference, retrieval time,
original date strings, parties, territory, rights scope, and explicit
`exclusive`, `non_exclusive`, or default `unknown` semantics. Party, asset, and
patent relationships are created only from a unique exact namespaced
identifier. Names alone are stored as source facts and are not entity links.
The API does not scrape/extract licensing terms or make legal/FTO conclusions.
Tenant scope derives from verified identity claims; tenant-private entities
remain outside global graph/search projections.

`GOOGLE_PATENTS_BASE_URL`, `GOOGLE_PATENTS_TIMEOUT`,
`GOOGLE_PATENTS_MAX_RETRIES`, `GOOGLE_PATENTS_BACKOFF_SECONDS`,
`GOOGLE_PATENTS_REQUESTS_PER_SECOND`, and `GOOGLE_PATENTS_PAGE_SIZE` configure
the adapter. The public source may throttle or change its response format;
see `PHASE_8_IMPLEMENTATION.md` for scope and validation limitations.