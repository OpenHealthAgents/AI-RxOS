# Phase 7 — Regulatory Intelligence

## Status

**COMPLETE WITH DOCUMENTED LIMITATION**

Phase 7 adds one production-oriented regulatory source path, openFDA
Drugs@FDA, to the existing Literature durable job system and canonical
evidence architecture. Phases 2–6 were not reopened or reimplemented.

## Implemented source and flow

```text
openFDA Drugs@FDA search
  -> application/submission response
  -> normalized Literature regulatory event + content-hashed raw snapshot
  -> durable tenant-scoped job offset/record checkpoint
  -> stable FDA application/submission event identity
  -> KG canonical reconciliation
  -> source record -> source-fact observations -> claims -> supporting evidence
  -> transactional PostgreSQL projection outbox
  -> existing Neo4j / OpenSearch projection workers
```

`FDARegulatoryConnector` in `services/literature/app/connectors/sources.py`
uses openFDA's search expression directly; no second regulatory query syntax
is introduced. Each valid submission in an FDA Drugs@FDA application becomes
one normalized event with the source ID `FDA:<application-number>:<submission-number>`.
The raw application and submission objects, stable FDA source URL, API
endpoint, query, source status/type, parser version, and SHA-256 snapshot hash
are retained. Malformed applications or submissions are isolated and retained
as job dead letters rather than preventing valid submissions from the same
response page from being processed.

The existing PostgreSQL-backed Literature job stores query, tenant, status,
retry state, page size, application offset, completed record keys, seen
offsets, progress, and dead-letter items. A persisted completion marker makes
completion recoverable if the process stops after the final checkpoint write.
Interrupted records are safely replayed through idempotent Literature
upserts and KG reconciliation. Regulatory jobs reject empty queries and fail
closed with HTTP 503 if the durable PostgreSQL path is unavailable; they do
not use the legacy in-memory job fallback.

## Identity and reconciliation

The source event identity is the FDA application number plus submission
number. New source content changes the content-hashed source-record version,
not the stable event identity. Literature current rows are unique by source,
event ID, and tenant scope; snapshots are deduplicated by source, event ID,
content hash, and tenant scope.

KG adds the namespaced `fda:submission_event` identifier and uses the existing
B01 canonical reconciliation flow. Exact identity matches are reused;
unresolved/ambiguous candidates are not selected arbitrarily. A unique exact
`fda:product_number` identifier may link the event to a canonical
therapeutic asset. Product brand and sponsor names do not create canonical
entities or links by themselves.

## Provenance, evidence, and time

KG source records carry the regulator, jurisdiction, event ID, query,
retrieval time, source URL, content hash, parser/source metadata, and a
reference to the Literature raw snapshot. Source facts remain distinct
append-only observations. Each fact has a `source_fact` claim and supporting
evidence link tied to the originating observation and source record. Canonical
event attributes are emitted through the existing transactional projection
outbox. Source status is not elevated to a reviewed scientific conclusion.

FDA submission status dates are retained verbatim (for example, `20240115`).
They are not parsed into fabricated exact timestamps. Retrieval time,
Literature database ingestion, canonical source/observation/claim availability,
and source event date remain distinct. Regulatory history supports timezone-
aware `as_of` filters using the existing Phase 4 knowledge-state semantics;
later arrivals do not appear in earlier knowledge snapshots.

## API and configuration

The existing authenticated Literature job APIs are reused:

- `POST /api/v1/ingestion` with `source: "regulatory"` and an explicit
  openFDA Drugs@FDA search expression.
- Existing job status, checkpoint, retry, cancellation, and dead-letter APIs
  remain tenant-scoped.
- Existing paper inspection APIs expose the normalized row, snapshot-related
  metadata, and reconciliation status.
- KG exposes authenticated
  `POST /api/v1/canonical/regulatory-events/ingest` and
  `GET /api/v1/canonical/regulatory-events/history`; history supports event,
  regulator, jurisdiction, event type/status, pagination, and `as_of`.

FDA source settings are `FDA_REGULATORY_BASE_URL`,
`FDA_REGULATORY_TIMEOUT`, `FDA_REGULATORY_MAX_RETRIES`,
`FDA_REGULATORY_BACKOFF_SECONDS`,
`FDA_REGULATORY_REQUESTS_PER_SECOND`, and `FDA_REGULATORY_PAGE_SIZE`.
Retries are bounded for HTTP 429, transient 5xx, and transport/timeout
failures; permanent HTTP 4xx errors are not retried. Pacing defaults to one
request per second and is shared across connector instances in a process.

## Tenant scope and projections

Literature rows, snapshots, and jobs retain tenant ownership. KG derives
organization scope from its verified principal; tenant A cannot read tenant
B's private regulatory event, while tenant-scoped principals can read public
events. Unscoped access does not expose private rows. Global canonical events
use the existing Neo4j/OpenSearch outbox projection. Tenant-private canonical
events are deliberately not globally projected under the existing Phase 2
projection limitation. No tenant-safety changes were made to legacy graph or
search paths.

## Closure matrix

### Requirement results

| Capability | Result |
| --- | --- |
| Official regulator adapter and deterministic query input | Implemented for openFDA Drugs@FDA |
| Application/submission normalization and raw provenance | Implemented; raw snapshots stored in Literature PostgreSQL |
| Stable event identity and repeat ingestion | Stable FDA application/submission event identity; idempotent |
| Durable offset/checkpoint and interrupted recovery | Implemented with persisted per-record keys and completion marker |
| Bounded HTTP/transport retry and malformed-record isolation | Implemented and deterministically tested |
| Request-rate control | Shared among FDA connector instances within one process; no distributed coordinator |
| Canonical identity, source facts, claims/evidence, and outbox | Implemented through KG canonical repository |
| Historical knowledge-state and tenant isolation | Implemented through existing Phase 4/API boundaries and tested |
| Exact product-to-asset reconciliation | Unique FDA product-number matches only |
| Search filters | Canonical history provides structured filters; OpenSearch does not expose dedicated regulator/event facets |
| Coverage of regulators and FDA source types | Drugs@FDA only; other authorities and FDA safety/labeling feeds are not ingested |

### Phase closure state

| Phase | Closure state |
| --- | --- |
| Phase 2 — Canonical foundation | Closed |
| Phase 3 — Evidence architecture | Closed |
| Phase 4 — Temporal intelligence | Closed with documented limitation |
| Phase 5 — PubMed ingestion | Closed with documented limitation |
| Phase 6 — ClinicalTrials.gov ingestion | Closed with documented limitation |
| Phase 7 — Regulatory intelligence | Complete with the limitations listed below |

## Limitations

- Coverage is limited to openFDA Drugs@FDA application submissions. FDA
  labeling/safety feeds and other regulators such as EMA and PMDA are not
  implemented.
- openFDA reports result totals in applications, while this pipeline counts
  flattened submission events. Job totals are finalized from successfully
  processed and dead-lettered events only when a job completes.
- openFDA offset pagination cannot continue beyond its 25,000 skip-offset
  window. The final accessible page is processed, then the job fails
  explicitly if more results remain; the query must be narrowed.
- Request pacing is shared within one process but not coordinated across
  service replicas.
- Structured regulator/jurisdiction/type/status filtering is available on
  the canonical history API, not as dedicated OpenSearch facets.
- The canonical outbox behavior is PostgreSQL-tested, but this validation
  environment did not provide live Neo4j/Search endpoints for a Phase 7
  projection smoke; the existing projection integration tests were skipped
  for that environment reason.
- No automatic product/sponsor-to-asset/company, indication, safety, or
  labeling relationships are inferred from names or regulatory text.
- Tenant-private canonical events are not projected into global graph/search
  indexes under the existing canonical projection boundary.
- The API's partial source event date remains a source string; canonical
  timestamp columns do not provide partial-date precision semantics.

## Validation

The live source smoke was read-only and did not persist its FDA record. A
focused adapter run returned nine normalized submissions for the known
`NDA021248` application; the first was
`FDA:NDA021248:18` (`AP`, source date `20190620`) with its raw source payload
and content hash preserved. The deterministic suite uses mocked FDA responses.
Database-backed tests used the isolated PostgreSQL validation database.

- `python -m pytest -q services/literature/tests/test_regulatory_ingestion.py services/literature/tests/test_orchestrator.py -k "regulatory or FDA"` — 10 passed, 7 deselected.
- `python -m pytest -q services/kg/tests/test_pubmed_ingestion.py -k regulatory` — 4 passed, 6 deselected, including history API filtering/validation, evidence, temporal behavior, and tenant visibility.
- `python -m pytest -q services/literature/tests/test_pubmed_persistence.py -k regulatory` — 2 passed, covering PostgreSQL checkpoint reload after simulated restart and one current event row with two versioned snapshots.
- `python -m pytest -q services/literature` — 140 passed.
- `python -m pytest -q -rs services/kg/tests` — 96 passed, 2 skipped. The skipped tests require live Neo4j/Search plus B10 internal-token settings or live canonical projection endpoints; PostgreSQL-backed canonical/reconciliation tests ran.
- `cd services/search; go test ./...` — passed.
- `git diff --check` — passed. Git emitted line-ending normalization warnings for unrelated pre-existing modified files.
- Pylance diagnostics — no errors in the changed FDA processor/configuration/routes, KG repository, or regulatory tests.

Pytest emitted existing `pytest-asyncio` loop-scope and
`pythonjsonlogger` import deprecation warnings; neither affected test results.
