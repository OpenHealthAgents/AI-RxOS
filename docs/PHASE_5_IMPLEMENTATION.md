# Phase 5 — PubMed Ingestion

## Status

**COMPLETE WITH DOCUMENTED LIMITATION**

Phase 5 extends the existing `services/literature` acquisition and job
framework and writes source-backed records through the `services/kg`
canonical API. Phases 2 and 3 remain closed. Phase 4's canonical knowledge
state and `as_of` semantics remain unchanged.

## Ingestion path

```text
NCBI ESearch / EFetch
  -> normalized Literature article + source snapshot
  -> PMID / PMCID / DOI identifiers
  -> existing Literature NLP candidate extraction
  -> KG B01 canonical reconciliation
  -> canonical source record and observations
  -> source-fact claim and supporting evidence link
  -> existing transactional projection outbox
  -> Neo4j / OpenSearch projection workers
```

`PubMedConnector` in `services/literature/app/connectors/sources.py` performs
NCBI ESearch discovery and EFetch XML retrieval. It accepts the existing NCBI
query expression unchanged (including explicit PMID expressions), uses
`retstart`/`retmax` for pages, and normalizes each `PubmedArticle`. The
`PubMedIngestionProcessor` orchestrates that adapter and reuses the Literature
NLP pipeline, the PostgreSQL manager, and `KGClient`; it does not create
canonical entities directly.

The parser retains the title, sectioned abstract and flattened abstract,
structured authors and author identifiers, author and article affiliations,
journal and issue details, publication types, languages, article dates, MeSH
terms, keywords, chemicals, grants, identifiers, parser version, query, raw
XML, and a content hash. Optional values remain absent/null when the source
does not supply them. Author mentions are not converted into canonical people
or companies.

## Identity, source records, and provenance

- PMID is the stable source identity (`source_id=PMID:<pmid>`) and is stored as
  `pubmed:pmid` in canonical identifiers.
- Present PMCID and DOI values are stored as `pmc:pmcid` and `doi:doi`.
- KG reconciliation checks exact namespaced identifiers before alias/name
  matching. Ambiguous candidates remain unresolved; NLP mentions are recorded
  as reconciliation candidates and are not auto-created as canonical entities.
- Literature stores one `literature_papers` row per PMID and visibility scope.
  Repeated ingestion updates that row. Source snapshots are deduplicated by
  source, PMID, payload hash, and tenant scope, while changed payloads remain
  available as distinct snapshots.
- Canonical `source_records` retain NCBI PubMed as source, PMID and payload
  version, stable PubMed URL, source metadata, parser/query provenance,
  retrieval time, and a reference to the Literature raw snapshot. Raw XML is
  held once in the Literature PostgreSQL JSONB snapshot, not duplicated in
  canonical provenance.
- PubMed's source record links to source-fact observations, the publication
  entity and namespaced identifiers, a `source_fact` claim, and a supporting
  evidence link. Extracted entities and relationships are retained separately
  as normalized observations with `literature_nlp` origin metadata.

## Time semantics

`publication_date_source` preserves PubMed's original date precision as text
(for example, `2019 Jun`), and structured article date values are retained in
source metadata. The pipeline does not convert year/month-only values into an
exact timestamp. `published_at` therefore remains null when the source does
not provide an instant that the current canonical timestamp schema can
represent faithfully.

Retrieval time is recorded separately from database-generated Literature and
canonical `ingested_at` values. It is retained in source provenance and the
Literature paper representation; it is not used as publication time.
Canonical claims/evidence continue to use Phase 4 knowledge-state availability
and valid-time semantics.

## Jobs, checkpointing, retries, and tenant scope

Ingestion jobs, status, query, progress, retry count, dead letters, tenant
ownership, auth context, and JSONB checkpoint are persisted in
`literature_ingestion_jobs`. Checkpoints record the ESearch page offset and
PMIDs completed on that page. A restarted worker recovers queued/running jobs,
re-fetches the interrupted page and skips completed PMIDs. Malformed records
are isolated into durable dead-letter items and checkpointed immediately;
replaying the page does not count the same malformed record twice.

NCBI request retries are bounded and exponentially backed off. Request pacing
is configured by `PUBMED_REQUESTS_PER_SECOND` (default 3 requests/second);
`PUBMED_MAX_RETRIES` and `PUBMED_BACKOFF_SECONDS` configure retry count and
base delay. `KGClient` also retries bounded transient KG failures. Failed jobs
can be replayed through the existing tenant-scoped retry API, bounded by
`INGESTION_MAX_RETRIES`; retries preserve the durable checkpoint and rely on
idempotent source/canonical persistence.

Literature source rows, raw snapshots, and jobs use forced PostgreSQL RLS and
organization filters. The verified job principal is re-signed for the internal
KG canonical request; KG derives write visibility from verified claims.
Tenant evidence stays tenant-scoped, public evidence follows the canonical
global-write policy, and unscoped private reads fail closed.

## Validation

Deterministic fixtures cover structured and missing publication metadata,
identifier normalization, source snapshots, idempotent PMID ingestion,
canonical source/observation/claim/evidence lineage, tenant boundaries,
knowledge-state time behavior, request pacing, bounded HTTP retry, malformed
record dead-lettering, and restart/resume from a persisted checkpoint.

Validation against an isolated PostgreSQL database using the Compose
non-superuser runtime role:

- `python -m pytest -q services/literature` — 122 passed.
- Focused PubMed Literature tests — 11 passed after the recovery and retry
  changes.
- `python -m pytest -q services/kg/tests` — 89 passed, 2 downstream
  projection/end-to-end tests skipped because their dedicated live test
  settings were not supplied.
- `cd services/search; go test ./...` — passed.
- `git diff --check` — passed.
- The B06 legacy tenant-enforcement integration test — 1 passed against its
  own disposable PostgreSQL database; a connection-target assertion prevents
  it from writing fixtures into the suite database.
- Live NCBI smoke: query `31912902[PMID]` returned PMID 31912902 with source
  date precision and raw XML. No PubMed record was written into the shared
  application database by the smoke test.

## Limitations

- NCBI paging uses query plus `retstart`; a resumed job reconstructs the
  current page by rerunning ESearch. If the upstream result set or its
  ordering changes during a long interruption, offsets could shift. A durable
  full PMID manifest or NCBI History-server snapshot is not currently stored.
- Request pacing is process-local. Multi-replica deployments must coordinate
  their aggregate NCBI request rate operationally.
- Date-only/month-only publication precision is preserved in source metadata
  but is not yet modeled as a typed partial date in canonical PostgreSQL.
- Database failures fail the current job and are recoverable through the
  existing bounded retry API; the Literature persistence write does not have
  an independent automatic database retry loop.
- The two skipped KG tests exercise downstream projection/API paths rather
  than PubMed ingestion. Their live endpoints were not configured for this
  isolated validation run.

These are bounded limitations of source-set stability, multi-replica rate
coordination, temporal representation, and retry automation; they do not
change the tested deterministic ingestion, identity, provenance, or
tenant-isolation behavior.
