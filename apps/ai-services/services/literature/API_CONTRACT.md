# Literature Service API Contract

## Base URL
- Local service port: `8082`

## Endpoints

### `GET /healthz`
Returns service health.

Response:
```json
{"status": "ok", "service": "literature"}
```

### `GET /metrics`
Returns in-memory counters from `MetricsRegistry`.

### `POST /api/v1/ingestion`
Creates and enqueues an ingestion job, returning HTTP 202 and the persisted job
envelope.

Request body:
```json
{"source": "pubmed", "query": "trastuzumab HER2"}
```

Supported `source` values:
- `pubmed`
- `pmc`
- `clinicaltrials`
- `regulatory`
- `aacr`
- `asco`
- `sabcs`
- `esmo`
- `biorxiv`
- `medrxiv`
- `patents`
- `company_websites`

Response fields:
- `id`
- `source`
- `query`
- `status`
- `createdAt`
- `page_size` (optional, 1–1000; for ClinicalTrials.gov and regulatory jobs)

### `GET /api/v1/ingestion/{job_id}`
Returns the tenant-scoped persisted job, including status, progress, retry
state, dead letters, and checkpoint.

### `POST /api/v1/analyze`
Runs parser, NER, summarization, relationships, duplicate detection, and evidence ranking on ad hoc text.

### `GET /api/v1/papers`
Lists persisted Literature papers when PostgreSQL is configured; in-memory
fallback behavior remains for legacy/test operation.

### `GET /api/v1/papers/{paper_id}`
Returns persisted paper metadata, including PubMed identifiers, source
metadata, retrieval/ingestion times, and canonical reconciliation status when
PostgreSQL is configured.

## Notes
- PubMed is acquired with NCBI ESearch/EFetch through the existing Literature
  connector. NCBI query expressions, including deterministic PMID queries,
  are passed through without introducing another query language.
- PubMed jobs persist page checkpoints and completed PMID identities. Failed
  jobs can be retried through the existing bounded retry endpoint.
- PubMed papers and raw source snapshots are PostgreSQL-backed when configured.
  The canonical KG boundary stores source records, namespaced identifiers,
  observations, claims/evidence, and projection outbox events.
- ClinicalTrials.gov jobs use API v2 and the same durable job endpoints. A
  direct `NCT########` query performs deterministic NCT lookup; other query
  text is sent to the official term-search parameter. The adapter preserves
  opaque continuation tokens, full normalized study metadata, and the raw
  source snapshot. KG uses `clinicaltrials:nct_id` for canonical identity and
  retains source-fact observations, claims, evidence, and current-attribute
  projection updates. Source date precision is not expanded into invented
  timestamps. Disease/asset/company/publication links are not inferred from
  unverified study text.
- Regulatory jobs query the official openFDA Drugs@FDA endpoint using an
  explicit openFDA search expression. They use PostgreSQL-backed checkpoints,
  tenant-scoped raw snapshots, bounded retry/dead-letter handling, and the
  authenticated KG regulatory-event ingestion/history APIs. FDA application
  submissions have stable `FDA:<application>:<submission>` identity, preserve
  source status-date strings, and link assets only by a unique exact FDA
  product-number identifier. The API's 25,000 offset limit and other source
  coverage constraints are documented in `docs/PHASE_7_IMPLEMENTATION.md`.
- Trace IDs are propagated through the `X-Trace-ID` response header.
