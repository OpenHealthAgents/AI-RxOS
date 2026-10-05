# AI-RxOS Data Model Baseline

## Purpose

This is the Phase 0 data-model constitution. It records current ownership and
the invariants future schema work must preserve. It is not a claim that every
future table already exists.

## Evidence Layers

1. **Source records**: immutable source identifiers, retrieval timestamps,
   source URLs, usage metadata, and raw payload references.
2. **Normalized observations**: parsed scientific, clinical, regulatory, IP,
   commercial, and entity observations with confidence and source links.
3. **Temporal evidence**: observation validity, publication/retrieval time,
   supersession, and the knowledge cutoff used by an evaluation.
4. **Canonical entities**: target-agnostic assets, compounds, biologics,
   modalities, diseases, indications, biomarkers, companies, trials, patents,
   publications, and relationships.
5. **Derived features**: reproducible calculations or model inputs with
   definitions, versions, source observation IDs, and uncertainty.
6. **Predictions and AI inference**: model outputs and LLM claims with
   model/prompt/tool provenance; never stored as source facts.
7. **Human decisions**: reviewer identity, decision, rationale, override, and
   timestamp.

## Existing Owners

- Auth organizations, workspaces, users, memberships, sessions, and audit
  foundations: `services/auth/migrations/`.
- LLM Wiki pages/chunks/versions/provenance: `services/llm-wiki/migrations/`.
- Graph entities, relationships, graph versions, and evidence scoring:
  `services/kg/app/`.
- Literature document/job/extraction behavior: `services/literature/app/`.
- Search embeddings/index metadata: `services/search`.

## Required Future Invariants

- Every evidence-backed claim links to source observations.
- Every tenant-owned record carries tenant scope where applicable and is
  filtered inside its owning service.
- Canonical identity is separate from source-specific identifiers.
- Corrections supersede rather than erase evidence.
- Contradictory observations remain queryable.
- Derived features identify input observations and computation version.
- Recommendations store evidence snapshots, scoring/model versions,
  explanations, uncertainty, and human review state.
- No schema is created for a single target, disease, company, or modality.

## Current Risks

Literature durable migrations, tenant enforcement, unified audit storage, and
canonical entity resolution are incomplete. Detailed schema documents describe
the target state; they do not prove those tables already exist.

## Phase 2 Canonical Foundation and Phase 3 Evidence Architecture

The canonical API and migration owner is the existing `services/kg` service.
Its PostgreSQL `canonical` schema is authoritative for canonical identity,
namespaced identifiers, aliases, source records, relationships, observations,
claims, evidence links, and the projection outbox. The existing shared Postgres
instance is reused; no database or service was added. Literature remains the
source acquisition and publication parsing owner. Existing `literature_papers`
rows are migration inputs; they are not silently copied or deleted.

### Phase 3 evidence model

Phase 3 is implemented as an additive evidence layer on top of the existing
source-record and observation model. The key tables are:

- `canonical.claims` stores claim text or structured claim payloads with
  `claim_type`, `confidence`, `statement`, `entity_id`, provenance, and time
  windows. Allowed claim families are `source_fact`, `derived_claim`,
  `inference`, and `prediction`.
- `canonical.evidence_links` stores the `supporting`, `contradicting`,
  `context`, and `derived` links between a claim and either an observation or
  a source record. These rows preserve contradiction without overwriting the
  opposite polarity.

Each claim references its source record and optionally the originating
observation. Every evidence row tracks tenant visibility and a valid-time window
when present. This keeps evidence lineage explainable and durable without
replacing the underlying observation system.

### Entity Families and Identity

`canonical.entities` supports therapeutic assets, targets, diseases,
indications, biomarkers, companies, clinical trials, publications, patents,
regulatory events, mechanisms, combinations, and resistance mechanisms. The
entity family is validated; typed, extensible JSON attributes add known
fields without requiring a schema redesign for new modalities or targets.
Assets support SMALL_MOLECULE, ANTIBODY, ADC, PROTEIN, PEPTIDE, CELL_THERAPY,
GENE_THERAPY, RNA_THERAPY, RADIOPHARMACEUTICAL, VACCINE, and OTHER.

`canonical.identifiers` uses `(namespace, identifier_type, normalized_value,
visibility scope)` uniqueness. `canonical.aliases` preserves development,
generic, brand, alias, and synonym labels plus source and review state. Names
are normalized for exact lookup only. Duplicate normalized names remain valid
separate entities; `/resolve-name` returns `ambiguous` rather than merging.
Exact namespaced identifiers resolve directly. An alias resolves automatically
only after explicit verification; unreviewed matches remain candidates.

### Observation, Provenance, and Time

`canonical.source_records` stores source namespace/ID, type, URL, published,
updated, observed, and ingestion times, payload reference/hash, and provenance.
Every entity links to its creation source; every identifier, alias, relationship
observation, and standalone observation references a source record. Lifecycle
status is also recorded as an observation. Observations carry kind
(`source_fact`, `normalized_observation`, `hypothesis`), review state,
confidence, valid-time range, source timestamps, normalizer version, optional
supersession, and reviewer identity/time. Observation rows are append-only;
corrections insert a superseding record. Derived features and decisions are not
part of this schema.

### Temporal Query Semantics (Phase 4)

Temporal values have separate meanings and remain nullable when the source does
not supply them:

- Source `published_at`, `source_updated_at`, and `observed_at` describe source
  and event history; none is substituted for platform availability.
- Source-record and observation `ingested_at` fields record when those rows
  became available to AI-RxOS. Observation `manually_verified_at` records
  reviewer verification separately.
- Observation, claim, and evidence-link `valid_from` / `valid_to` represent
  domain-effective validity. The interval is closed and inclusive at both
  bounds; null bounds are unbounded.
- Claim/evidence-link `created_at` is the platform availability time for those
  records; they do not currently have independent ingestion columns.

The canonical claim list and lineage `as_of` APIs use knowledge-state
semantics: source records, observations, claims, and evidence created/ingested
after the cutoff are excluded, as are rows whose validity interval does not
contain it. A late-arriving source can therefore describe an older publication
while remaining unavailable to earlier AI-RxOS knowledge snapshots. Publication
and observation timestamps stay visible in lineage but do not imply availability.

### PostgreSQL, Neo4j, and Search Ownership

- PostgreSQL `canonical` is the system of record. Its migrations are ordered,
  tracked, transactionally applied under an advisory lock, and do not depend
  on Auth-owned table foreign keys.
- Neo4j remains owned by `services/kg`. Global canonical entities and
  relationships project idempotently under stable canonical UUIDs to
  `CanonicalEntity`/`CANONICAL_RELATIONSHIP` nodes/edges.
- OpenSearch remains owned by `services/search`. Its documents carry
  `canonical_id` and `entity_type`; they are rebuildable projections, never
  identity authorities.
- The PostgreSQL outbox leases global events with `SKIP LOCKED`, bounded retry
  backoff, and delivery/error metadata. Tenant events are deliberately not
  projected while existing graph/search read paths lack tenant enforcement.

### Tenant Boundary and Limitations

Canonical APIs verify HS256 bearer tokens independently and derive organization
scope only from verified claims. Client bodies cannot select an organization.
PostgreSQL queries apply explicit visibility filters and forced RLS permits
global rows plus only the caller's organization; missing scope sees no private
rows. The shared development DB's privileged connection can bypass RLS, so the
explicit repository predicates are the enforced application boundary. Global
writes and reviewer state require operator/reviewer roles. Gateway-wide claim
propagation and legacy KG/Search route hardening remain separate work.

The demo fixture marks every record synthetic and all relationship assertions
as unreviewed hypotheses; it contains no fabricated trial, publication, patent,
regulatory decision, or verified efficacy claim. The Compose demo root CA and
hostname are now trusted explicitly by Search (TLS verification remains on),
and a live synthetic entity has projected through Neo4j/OpenSearch. Managed
deployment CA handling and tenant-private projections remain unverified.

### PubMed Source Records and Evidence (Phase 5)

The existing Literature owner stores normalized PubMed papers and source
snapshots in PostgreSQL. `literature_papers` is idempotent by source, PMID,
and tenant scope; `literature_source_snapshots` deduplicates raw XML snapshots
by PMID, content hash, and tenant scope. Canonical source records reference
the Literature snapshot rather than duplicating raw XML.

Canonical publication identity uses namespaced identifiers: `pubmed:pmid`
(required), plus `pmc:pmcid` and `doi:doi` when supplied. The KG B01
reconciliation hierarchy resolves exact identifiers before aliases or names;
ambiguous and unresolved candidates are not arbitrarily merged. Article
metadata, sectioned abstracts, authors and author IDs, journal, publication
date source precision, article dates, MeSH, keywords, chemicals, grants, and
other identifiers remain in source metadata/observations.

PubMed retrieval time is provenance, separate from source publication time
and database ingestion availability. Partial publication dates remain source
strings; they are not converted to fabricated `TIMESTAMPTZ` values.
Source-observed article metadata creates source-fact observations and an
indexed-publication source-fact claim with supporting evidence. NLP
entity/relationship candidates are separate normalized observations and keep
their extraction origin and source record. They are not promoted to verified
claims or canonical entities merely because the model extracted them.

Ingestion job query, tenant, status, progress, retry state, checkpoint, and
dead-letter items are durable. The checkpoint tracks the current ESearch page
and completed PMIDs. See `PHASE_5_IMPLEMENTATION.md` for resume behavior and
known limits of offset paging, source precision, and process-local rate
limiting.

## ClinicalTrials.gov Source Records (Phase 6)

ClinicalTrials.gov API v2 studies are persisted by the Literature service as
normalized trial records and content-hashed raw snapshots, scoped by NCT ID
and tenant. The official NCT identifier is the stable source identity;
secondary registry identifiers remain in the normalized study metadata.
Canonical trial entities use the namespaced `clinicaltrials:nct_id`
identifier, while each changed source payload receives a versioned source
record and a reference to the corresponding Literature snapshot.

The adapter retains study identification, status, design, phases, enrollment,
sponsor/collaborators, conditions, interventions, arms, outcomes, eligibility,
locations, references, and results when present. It preserves source date
strings at their published precision (including year-only and year-month
values); it does not invent an exact publication or observation instant.
Retrieval/ingestion time and canonical knowledge-state availability remain
separate from the registry's study dates.

Source facts are represented by source-linked observations, source-fact
claims, and supporting evidence. Revised source content appends a new
versioned lineage and updates the current canonical trial attributes with an
idempotent projection-outbox event. Tenant jobs and private source records
remain scoped to their verified organization. The API does not create
canonical disease, asset, company, or publication links from study text alone;
the structured source facts (including references and intervention details)
remain available for a later identifier-backed reconciliation rather than
being guessed from names.

## FDA Regulatory Source Records (Phase 7)

The Literature service stores openFDA Drugs@FDA submissions as tenant-scoped
normalized records and content-hashed raw source snapshots. A stable event ID
combines application and submission identifiers; changes to the raw source
snapshot create a new canonical source-record version without changing event
identity. The payload retains application/product/sponsor data, submission
status/class/date fields, source query, source URL, endpoint, parser version,
retrieval time, and raw response reference.

KG reconciles a namespaced FDA submission-event identifier before creating
the canonical regulatory event. Source facts are separate append-only
observations linked to source-fact claims and supporting evidence. Exact
FDA product-number identifiers can create an event-to-asset relationship
only when resolution is unique; product and sponsor display names are not
treated as canonical entity identity. The event projection is emitted through
the existing PostgreSQL outbox. No second evidence store or job framework is
introduced.

The FDA source status date is retained as its original string, including its
precision and source representation. It is not promoted into an exact
event-time or `TIMESTAMPTZ` value. Retrieval time and PostgreSQL/canonical
availability remain separate, so history filters use the existing Phase 4
knowledge-state `as_of` semantics. Public ingestion requires the existing
operator/system scope; tenant-scoped jobs create organization-visible records
and preserve the current rule that tenant-private canonical events are not
projected into global graph/search indexes.

## Patent and Licensing Evidence (Phase 8)

Phase 8 extends the existing canonical entity family with `patent_family` and
`licensing_event` while retaining `patent` as the publication-level identity.
A patent identifier is namespaced by jurisdiction and identifier kind; a
patent-family identifier uses a separate namespace. Repeated source versions
reconcile to the same patent/family entity instead of creating a new entity.
Literature retains one current row per patent publication ID and tenant, while
content-hashed source snapshots retain each returned source version.

The Google Patents adapter preserves publication/application/grant numbers
where returned, family metadata, title, search excerpt, inventor, assignee,
filing/publication/grant date strings, language, query, parser version, source
URL, retrieval time, and a reference to the original response snapshot.
Inventor, applicant, and assignee fields are not substituted for each other.
Source strings such as `2019` and `2018-06` remain strings; an incomplete date
is not converted into an exact timestamp.

Canonical patent facts and structured licensing-event terms are append-only
source-fact observations, each with a source-fact claim and supporting
evidence link back to the versioned source record. Event source identity,
source name/URL, retrieval and ingestion availability, event/effective/
expiration date strings, territory, rights scope, and exclusivity state are
kept separately. Exclusivity defaults to `unknown`. Contradictory source
statements remain separate observations/claims. A structured relationship to
a company, asset, or patent requires exactly one visible match for a
namespaced identifier; display-name-only party matching is not performed.
Patent-family membership uses the existing source-backed canonical
relationship and outbox.

IP history uses the existing Phase 4 `as_of` knowledge-state semantics:
source records, observations, and entities unavailable at the cutoff are
excluded. Source event/publication date strings remain source facts rather
than substitutes for knowledge availability or invented exact valid-time
instants. Global IP entities and relationships use the existing Neo4j/
OpenSearch outbox projections; tenant-private data remains unprojected under
the existing projection boundary.

Google Patents is an aggregator rather than an authoritative patent office
register. Phase 8 does not ingest USPTO/EPO/WIPO assignment history, infer
current legal ownership from a search result, automatically discover or parse
licensing disclosures, determine enforceability, or provide
freedom-to-operate analysis. Those remain explicit source-coverage and
legal-review limitations.