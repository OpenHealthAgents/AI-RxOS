# Phase 8 — IP & Licensing Intelligence

## Status

**COMPLETE WITH DOCUMENTED LIMITATION**

Phase 8 extends the existing Literature durable job system and KG canonical
evidence model. Phases 2–7 were not reopened.

## Implemented flow

```text
Google Patents public search
  -> Google Patents XHR result
  -> normalized Literature patent row + content-hashed source snapshot
  -> durable tenant-scoped job/page/record checkpoint
  -> jurisdiction-scoped patent ID reconciliation
  -> canonical patent + optional family
  -> source-fact observations -> source-fact claims -> supporting evidence
  -> transactional projection outbox -> existing Neo4j/OpenSearch workers

Source-backed licensing/assignment disclosure
  -> typed canonical licensing event + source record
  -> identifier-only party/asset/patent reconciliation
  -> observations -> claims/evidence -> relationship/outbox
```

## Requirement matrix

| Requirement | Implementation | Validation / result |
| --- | --- | --- |
| Source acquisition | Google Patents `/xhr/query`; explicit query or publication number; configurable bounded HTTP retries and process-local request pacing | Deterministic mocked adapter tests; controlled live request initially returned a source payload, subsequent requests received HTTP 503 (external throttling) |
| Patent normalization | Publication number, jurisdiction, title, source excerpt, inventor, assignee, filing/publication/grant dates, family metadata, language, and full returned result snapshot retained | Adapter parser tests |
| Patent identity | Namespaced jurisdiction + publication/application/grant identifiers; B01 reconciliation; family identity separately namespaced | PostgreSQL integration verifies stable canonical patent/family identity and identifier handling |
| Durable Literature identity | One current patent row per publication ID and tenant; content-hash snapshots remain versioned | PostgreSQL snapshot/idempotency test |
| Durable jobs | Existing PostgreSQL job table; source page token and completed record IDs checkpointed per page; restart resumes current page; durable job status remains tenant-scoped | In-process interruption/resume test and PostgreSQL checkpoint recovery test |
| Retry / malformed source data | Bounded 429/5xx/transport retry; malformed result and canonical 409/422 payload are isolated to dead-letter entries; transient database/KG errors fail the job for bounded job retry | Deterministic retry, malformed-record, and processor tests |
| Patent-family identity | Optional family IDs become canonical family entities and source-backed membership relationships | PostgreSQL integration checks stable family entity and identifier |
| Licensing/assignment data | Typed, authenticated canonical event ingest stores source URL/hash, parties, asset/patent identifiers, territory, rights/field, source date strings, and `unknown` exclusivity default | PostgreSQL test verifies unknown semantics, evidence lineage, and exact namespaced links |
| Observations and evidence | Every normalized patent/event fact is a source-fact observation with source-fact claim and supporting evidence; contradictions remain versioned | PostgreSQL integration verifies observation/claim/evidence deduplication and claim lineage |
| Temporal semantics | Original date strings retain precision; retrieval, source observation, and canonical availability are separate; IP history uses Phase 4 knowledge-state `as_of` | PostgreSQL integration verifies the earlier status is visible only before the later source version |
| Tenant / public boundaries | Canonical scope derives from verified principal; exact identifier links are visibility-filtered; private data remains outside global projection | PostgreSQL integration verifies tenant B cannot see tenant A private patent |
| Projections and Search | Canonical IP entities/relationships use existing transactional outbox and generic graph/search projection logic; private projection boundary unchanged | Outbox behavior covered by existing canonical projection regressions |
| Legal boundary | No ownership, enforceability, exclusivity, or FTO conclusion is inferred from a name/search result; explicit source terms remain source facts | Schema default and deterministic integration assertions |

## Identity and provenance

The Literature row uses the publication number and tenant as its stable current
identity. Content-hashed snapshots retain source versions. The canonical KG
uses B01 reconciliation with jurisdiction-scoped namespaced identifiers;
application and grant numbers are added when returned, and an optional
Google-Patents family identifier produces a distinct family entity.
Ambiguous/unresolved B01 outcomes are not selected arbitrarily.

Google Patents search results contain a source excerpt, not necessarily a
complete patent abstract. It is retained as an excerpt and is not misrepresented
as a full abstract. Inventor, applicant, and assignee fields are kept distinct;
missing fields stay unknown. The complete returned result object, source URL,
query, parser version, content hash, retrieval timestamp, and raw-snapshot
reference are retained. No arbitrary HTML/blob store was added.

Structured licensing and assignment events are submitted through the canonical
IP ingest endpoint with source provenance. Free-text party names remain source
facts. A party, asset, or patent relationship is created only when exactly one
visible canonical entity matches the submitted namespaced identifier. The
source event can be replayed idempotently; changed source hashes append a new
source-record/observation/claim lineage while preserving prior evidence.

## Time and tenant semantics

Google Patents date values and licensing event/effective/expiration dates
remain source strings, including year-only and year-month precision.
`published_at` or event instants are not fabricated. Retrieval timestamps are
recorded separately from canonical source/observation ingestion availability.
`GET /api/v1/canonical/ip/history` applies the canonical Phase 4
knowledge-state `as_of` cutoff to entity and source-fact availability. It does
not treat the publication date as the time the platform learned the fact.

The existing verified principal controls global versus organization scope.
Tenant-private canonical events are not sent to the global Neo4j/OpenSearch
projection path. This change adds no unscoped data access.

## API and configuration

- `POST /api/v1/ingestion` accepts `source: "patent"` and a required patent
  identifier or Google Patents query. Existing job status, retry, cancel,
  checkpoint, and dead-letter APIs are reused.
- KG accepts authenticated `POST /api/v1/canonical/ip/patents/ingest` and
  `POST /api/v1/canonical/ip/licensing-events/ingest`.
- Canonical patent-family and licensing-event collection routes are available
  under `/api/v1/canonical/patent-families` and
  `/api/v1/canonical/licensing-events`.
- `GET /api/v1/canonical/ip/history` provides paginated patent, family, or
  licensing-event facts with a timezone-aware `as_of` parameter.
- `GOOGLE_PATENTS_BASE_URL`, `GOOGLE_PATENTS_TIMEOUT`,
  `GOOGLE_PATENTS_MAX_RETRIES`, `GOOGLE_PATENTS_BACKOFF_SECONDS`,
  `GOOGLE_PATENTS_REQUESTS_PER_SECOND`, and `GOOGLE_PATENTS_PAGE_SIZE`
  configure source access. Pacing is shared within one process, not across
  replicas.

## Validation

| Validation | Result |
| --- | --- |
| `python -m pytest -q services/literature/tests/test_google_patents_connector.py services/literature/tests/test_patent_ingestion.py` | 7 passed |
| `python -m pytest -q services/literature` | 148 passed; used a restricted Literature runtime DSN and separate schema-owner DSN for PostgreSQL persistence coverage |
| `python -m pytest -q services/kg/tests/test_ip_ingestion.py` | 2 passed against disposable PostgreSQL |
| `python -m pytest -q services/kg/tests` | 98 passed, 2 skipped |
| `go test ./...` from `services/search` | Passed; handler/search packages passed, remaining packages had no test files |
| `git diff --check` | Passed; Git emitted only existing working-copy LF-to-CRLF notices |
| Pylance problems on changed Python files | No errors reported |

The live smoke reached the public Google Patents XHR endpoint and observed its
JSON search-result structure. A later one-record request was HTTP 503, so a
complete live query-to-canonical end-to-end smoke could not be verified in
this environment. Mocked tests exercise the normalized result shape and do
not depend on public availability.

## Closure gaps and limitations

- Automated source coverage is Google Patents only. It is an aggregator, not
  an authoritative patent-office register; USPTO, EPO, WIPO, and other office
  feeds are not implemented.
- Patent assignment/ownership history is not acquired from official registers.
  The model can retain source-backed assignment events, but this phase does
  not autonomously discover or verify them.
- Licensing/assignment disclosure acquisition and term extraction are not
  automated. Structured event facts must be supplied with a source and remain
  unreviewed source facts until reviewed.
- The public Google endpoint can throttle, change format, and return excerpts
  rather than full abstracts. Its rate limit is process-local.
- Source date strings are not exact valid-time intervals. Historical `as_of`
  means what AI-RxOS knew at the cutoff, not a legal opinion on ownership at
  that date.
- No enforceability, infringement, exclusivity, ownership, or freedom-to-
  operate conclusion is produced. Legal review remains necessary.
- Existing global OpenSearch facets do not yet provide dedicated IP/licensing
  filters; global canonical projection uses existing generic entity/edge
  support, and private projection remains intentionally disabled.

## Phase closure state

| Phase | State |
| --- | --- |
| Phase 2 — Canonical foundation | Closed |
| Phase 3 — Evidence architecture | Closed |
| Phase 4 — Temporal intelligence | Closed with documented limitation |
| Phase 5 — PubMed ingestion | Closed with documented limitations |
| Phase 6 — ClinicalTrials.gov ingestion | Closed with documented limitation |
| Phase 7 — Regulatory intelligence | Closed with documented limitations |
| Phase 8 — IP & Licensing Intelligence | Complete with documented limitation |

**Next phase: Phase 9 — Search & Retrieval.**
