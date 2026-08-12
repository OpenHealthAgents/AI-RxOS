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
Starts a synchronous ingestion job and returns the persisted job envelope.

Request body:
```json
{"source": "pubmed", "query": "trastuzumab HER2"}
```

Supported `source` values:
- `pubmed`
- `pmc`
- `clinicaltrials`
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

### `GET /api/v1/ingestion/{job_id}`
Returns the persisted `IngestionJobState`, including:
- state
- attempts
- error
- final `result`

### `POST /api/v1/analyze`
Runs parser, NER, summarization, relationships, duplicate detection, and evidence ranking on ad hoc text.

### `GET /api/v1/papers`
Placeholder paper listing backed by in-memory `_PAPERS`.

### `GET /api/v1/papers/{paper_id}`
Placeholder single-paper lookup backed by in-memory `_PAPERS`.

## Notes
- `POST /api/v1/ingestion` currently executes the pipeline inline before returning.
- The service returns completed jobs even when a source yields zero documents; callers must inspect `result.items`, `result.limitation`, and `result.source_status`.
- Trace IDs are propagated through the `X-Trace-ID` response header.
