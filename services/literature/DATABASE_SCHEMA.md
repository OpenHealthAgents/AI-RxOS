# Literature Service Data Schema

## Current Persistence
The service does not yet persist Prompt 6 records into Postgres tables. Current durable state is a JSON file:

- `data/ingestion_jobs.json`

This is sufficient for local restart continuity but is not a replacement for a production database schema.

## Persisted Job Model
`IngestionJobState`

Fields:
- `id: str`
- `source: str`
- `query: str`
- `status: pending | running | parsing | processing | completed | failed | retrying | dead_letter`
- `created_at: str`
- `updated_at: str`
- `attempts: int`
- `max_retries: int`
- `error: str | null`
- `result: object | null`

## Normalized Literature Document Model
Each connector normalizes records into:
- `title`
- `abstract`
- `content`
- `authors`
- `published_date`
- `source`
- `source_id`
- `doi`
- `url`
- `journal`
- `metadata`

## Derived NLP Structures
- `structured_entities`
- `structured_summary`
- `relationships`
- `evidence_ranking`
- `evidence`
- `duplicates`

