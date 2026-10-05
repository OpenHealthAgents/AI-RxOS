# Phase 6 — ClinicalTrials.gov Ingestion

## Status

**COMPLETE WITH DOCUMENTED LIMITATION**

Phase 6 reuses the Literature durable ingestion jobs and KG canonical
architecture. Phases 2–5 remain closed. Phase 4 temporal and
knowledge-state semantics are unchanged.

## End-to-end path

```text
ClinicalTrials.gov API v2
  -> normalized Literature trial + content-hashed raw snapshot
  -> stable NCT source identity
  -> durable page-token/record checkpoint
  -> KG B01 reconciliation by namespaced NCT
  -> canonical source record + trial identifier
  -> source-fact observations
  -> source-fact claims + supporting evidence
  -> transactional canonical projection outbox
  -> existing projection workers
```

`ClinicalTrialsConnector` in `services/literature/app/connectors/sources.py`
is the shared adapter. `source: "clinicaltrials"` jobs in the existing
orchestrator are handled by `ClinicalTrialsIngestionProcessor`; no second job
framework or query syntax was added. NCT-shaped queries are sent through
`query.id`; other expressions use API v2 `query.term`.

The adapter retains the raw API study, content hash, and normalized
identification, status, design, enrollment, sponsor/collaborators, conditions,
keywords, interventions, arms, outcomes, eligibility, locations, references,
results, dates, source URL, API endpoint, query, and parser version where
present. The Literature database stores one normalized record per source/NCT
and deduplicated snapshots by source, NCT, content hash, and tenant. New
versions retain their snapshots and update the current normalized record.
KG source records reference those snapshots rather than copying the raw
payload.

## Identity and reconciliation

NCT IDs are normalized to uppercase and validated as `NCT` plus eight digits.
Canonical identity uses `clinicaltrials:nct_id`; content-hash source record
versions do not create a second trial entity. KG's existing B01 reconciliation
is used. Exact NCT identity is required for automatic canonical trial
creation/matching. Ambiguous or unresolved reconciliation does not select a
candidate, and its status is returned to the Literature record.

## Provenance, evidence, and time

Each versioned KG source record records ClinicalTrials.gov, NCT ID, query,
retrieval time, source URL, endpoint, parser version, content hash, and the
Literature raw-snapshot reference. Source facts are retained as unreviewed
source-fact observations with source record and property/value lineage.
Each observation has a source-fact claim and supporting evidence link. Source
extraction is not elevated to a reviewed scientific assertion.

Registry date fields remain their original source strings. A year-only or
year-month source date is not converted to a fabricated timestamp.
Publication/study dates, retrieval/observation information, database
ingestion, and canonical claim/evidence availability remain distinct.
Historical knowledge-state availability continues to use the existing Phase
4 canonical timestamps.

When a later source version changes current trial attributes, the canonical
entity attributes are merged with the new source attributes and an
`entity.upserted` outbox event is written transactionally. An unchanged
replayed payload produces no extra entity projection event; prior
version-specific observations, claims, and evidence remain available.

## Jobs, recovery, and failure isolation

The existing tenant-scoped Literature job persists the query, page size,
opaque API `nextPageToken`, completed NCT/malformed-record keys, seen page
tokens, progress, dead-letter items, retry state, and verified auth context in
PostgreSQL. Each completed record is durably checkpointed. An interrupted
page is fetched again after restart and already-checkpointed records are
skipped. Repeated pagination tokens fail explicitly rather than causing an
infinite loop.

HTTP 429, transient 5xx, and transport/timeout failures use bounded exponential
backoff; permanent 4xx errors are not retried. KG handoff retries use the
existing bounded `KGClient` behavior, and job retries use the existing
Literature retry controller. Malformed studies are isolated and dead-lettered
with source identifier, raw JSON, page token, and diagnostic. The persisted
checkpoint avoids duplicate dead letters when the page is resumed.

Pacing defaults to two requests per second and is configurable with
`CLINICALTRIALS_REQUESTS_PER_SECOND`. Pacing is per connector instance, not
distributed among replicas. All job and private Literature rows retain
verified tenant scope; KG derives visibility from the internal signed
principal. Public canonical reads retain the existing public visibility
rules, and unscoped private reads remain fail-closed.

## API and configuration

The existing `POST /api/v1/ingestion`, job status/retry/cancel/dead-letter,
and paper inspection APIs are reused. `page_size` is persisted with the job
and limited to 1–1000. The internal canonical handoff is
`POST /api/v1/canonical/clinicaltrials/ingest`.

Configuration:

- `CLINICALTRIALS_BASE_URL`
- `CLINICALTRIALS_TIMEOUT`
- `CLINICALTRIALS_MAX_RETRIES`
- `CLINICALTRIALS_BACKOFF_SECONDS`
- `CLINICALTRIALS_REQUESTS_PER_SECOND`
- `CLINICALTRIALS_PAGE_SIZE`

## Limitations

- Conditions, intervention names, sponsor names, and reference metadata are
  retained as source facts, but the ingestion path does not create disease,
  asset, company, or publication relationships from text alone. Name-only
  auto-linking could create false associations. PMID/reference identifiers
  are preserved for a future explicit identifier-backed linking policy.
- No separate incremental `since` filter is mapped for API v2; discovery uses
  the existing query expression and API continuation tokens.
- Request pacing is process-local; concurrent service replicas do not share a
  quota coordinator.
- Historical source date precision is preserved as text in observations and
  metadata. The canonical timestamp columns do not model partial registry
  dates as exact instants.
- Live ClinicalTrials.gov availability is not part of deterministic tests.
  Any smoke test result is recorded separately from mocked adapter tests.

## Validation

Deterministic adapter tests cover NCT normalization, source metadata and raw
payload preservation, year/month/full date strings, opaque pagination,
malformed-record isolation, transient and timeout retries, permanent HTTP
failure, retry exhaustion, request pacing, interrupted processing, resume,
deduplication, and repeated-token detection. KG PostgreSQL tests cover
canonical NCT identity, idempotent observations/claims/evidence, tenant
isolation, temporal source revisions, and current-attribute projection
updates.

Validation used the isolated PostgreSQL database and did not persist the
external smoke-test study:

- `python -m pytest -q services/literature/tests/test_clinicaltrials_ingestion.py services/literature/tests/test_pubmed_persistence.py -k clinicaltrial`
  — 7 passed, 2 deselected.
- `python -m pytest -q services/literature/tests/test_clinicaltrials_ingestion.py`
  — final adapter/recovery run: 6 passed.
- `python -m pytest -q services/literature` — final rerun after rate-limit
  first-request handling and timeout/pacing coverage: 129 passed.
- `python -m pytest -q services/kg/tests` — 92 passed, 2 skipped. The skipped
  tests require configured live Neo4j/Search projection endpoints and the
  B10 internal-token settings; the PostgreSQL canonical/reconciliation
  integration tests ran.
- `cd services/search; go test ./...` — passed.
- `git diff --check` — passed; Git emitted only existing line-ending
  normalization warnings for unrelated modified files.
- Pylance Problems checks — no errors in the edited ClinicalTrials adapter,
  processor, KG schema/repository, or focused tests.
- Live API v2 search and adapter smoke — passed against one `breast cancer`
  result (`NCT00343382`, `COMPLETED`); the adapter returned the normalized
  NCT, source date `2012-12`, raw source payload, and SHA-256 content hash. No live
  record was written to the database.

The full Literature run reported one existing third-party
`python-json-logger` deprecation warning; pytest-asyncio also emits a
configuration deprecation warning. Neither caused test failures.
