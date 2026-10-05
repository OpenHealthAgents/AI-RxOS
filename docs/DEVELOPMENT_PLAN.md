# AI-RxOS Development Plan

## Phase 0 Completed

This phase establishes the product constitution and code-backed baseline. No
major application functionality was rewritten.

### Already implemented or materially reusable

- Monorepo/tooling: Turborepo, pnpm, TypeScript, Go, Python, Docker, Helm.
- Identity foundation: `services/auth` JWT/session/RBAC/MFA/ABAC/audit code.
- Graph foundation: `services/kg` Neo4j CRUD/import/version/evidence paths.
- Literature prototype: connectors, parsing, extraction, normalization,
  deduplication, summaries, and local job/retry behavior.
- Search foundation: OpenSearch/hybrid/RRF/indexing code.
- Durable LLM Wiki: pages, chunks, versions, provenance, tenant RLS.
- Agent platform: `services/agents` runtime, jobs, registries, memory,
  streaming, redaction, and provider adapters.
- Shared UI primitives and deployment manifests.

### Partially implemented

- Tenant isolation and gateway propagation.
- BetterAuth adapter migration.
- Literature durable Postgres schema and workers.
- Search scale/tenant filtering and provider documentation.
- Event transport and graph consumers.
- Observability exporters, unified audit, workflows, reports, and monitoring.
- Production web/admin integration with authenticated scientific workflows.

### Not implemented or contract-level

- Concrete oncology domain agents and scientific tools.
- Canonical asset/entity resolution across sources.
- Temporal evidence and historical evaluation framework.
- Evidence-derived decision scoring.
- Molecule generation, medicinal chemistry, ADMET/safety, and real docking.
- Opportunity/licensing/IP/commercial intelligence.
- Durable Temporal/Kafka infrastructure, backups/DR, and multi-region ops.

## Phase 1 — Repository Assessment (Complete)

Repository state, ownership boundaries, deployment gaps, security findings, and
current/transition/target architecture are documented in
`CODEBASE_ASSESSMENT.md` and `AI_RXOS_ARCHITECTURE.md`.

## Phase 2 — Canonical Data Foundation (Complete)

### Implemented foundation

- KG owns the canonical PostgreSQL schema and APIs, with additive migrations tracked by the repo’s migration runner.
- Canonical identity, source provenance, identifiers, aliases, observations, relationships, and outbox events are implemented and validated.
- Neo4j and OpenSearch remain derived projections, not competing source-of-truth stores.
- The Phase 2 flow is proven end-to-end in the repository runtime: source record -> reconciliation -> canonical entity -> observation/relationship -> outbox -> Neo4j projection -> Search projection -> scoped retrieval.

### Verified completion state

Phase 2 is now complete within the repository’s tested architecture. The actual validation path passed for the canonical data model, migration safety, tenant boundaries, projection replay, and live search/graph retrieval.

## Phase 3 — Evidence Architecture (Complete)

### Implemented foundation

- The canonical model now includes durable `claims` and `evidence_links`, linked to the existing source-record and observation backbone.
- Claim provenance and evidence polarity are stored explicitly and remain queryable without an LLM reconstructing the source chain.
- Supporting and contradicting evidence are both persisted and retrieved distinctly.
- Live repository tests validate lineage, contradiction preservation, as-of filtering, and cross-tenant evidence isolation.

### Verified completion state

Phase 3 is complete within the repo’s canonical evidence architecture. The repository has actual end-to-end evidence lineage coverage and real PostgreSQL-backed validation.

## Phase 4 — Temporal Intelligence (Complete With Documented Limitation)

- Canonical claims and evidence support knowledge-state `as_of` queries against PostgreSQL.
- Availability (`ingested_at` / `created_at`) remains distinct from publication, event/observation, verification, and domain-validity timestamps.
- Closed/inclusive valid-time bounds, null endpoints, late arrivals, corrections, contradictions, timezone equivalence, temporal lineage, and tenant scoping are covered by deterministic live PostgreSQL tests.
- Historical snapshots are not yet exposed by legacy graph/Search APIs or every canonical endpoint; see `docs/PHASE_4_IMPLEMENTATION.md`.

## Compatibility and Change Policy

- Preserve service owners and the existing architecture.
- Keep migrations additive and verifiable.
- Do not duplicate auth, graph, or search ownership.
- Require executable evidence before documenting a capability as complete.

## Phase 5 — PubMed Ingestion (Complete With Documented Limitation)

- The existing Literature connector uses NCBI ESearch/EFetch, preserving
  structured article metadata, identifiers, source snapshots, and original
  publication-date precision.
- Durable PMID-keyed Literature records, tenant-scoped ingestion jobs,
  page/PMID checkpoints, bounded source/KG retries, and dead-letter handling
  are implemented.
- PubMed records pass through KG canonical reconciliation and retain
  source-linked observations, an indexed-publication claim, supporting
  evidence, and the transactional projection outbox.
- Phase 4 publication, retrieval, and knowledge-state availability semantics
  remain distinct and unchanged.
- Validation and bounded limitations are recorded in
  `PHASE_5_IMPLEMENTATION.md`.

## Phase 6 — ClinicalTrials.gov Ingestion (Complete With Documented Limitation)

- The shared Literature job system now has an official ClinicalTrials.gov API
  v2 adapter with NCT search, opaque page-token pagination, structured study
  normalization, raw snapshots, bounded HTTP retries, and configurable
  request pacing.
- Durable NCT-keyed records, tenant-scoped job checkpoints, malformed-record
  dead letters, restart/resume, and KG retry handoff are implemented.
- KG reconciles NCT identity and persists versioned source records,
  source-fact observations, claims, supporting evidence, and idempotent
  projection-outbox updates for changed current trial attributes.
- ClinicalTrials source dates retain their original precision; source
  retrieval and canonical availability remain separate. Study text is not
  automatically linked to disease, asset, company, or publication entities
  without deterministic identifier-backed reconciliation.
- Implementation, regression results, and bounded limitations are recorded
  in `PHASE_6_IMPLEMENTATION.md`.

## Phase 7 — Regulatory Intelligence (Complete With Documented Limitation)

- The Literature service includes an official openFDA Drugs@FDA adapter for
  explicit search expressions, application-level pagination, per-submission
  normalization, raw payload snapshots, bounded retries, and process-wide
  request pacing within each service process.
- Tenant-scoped durable jobs checkpoint submission identities and offsets,
  isolate malformed records, resume after database/KG interruptions, and
  fail closed rather than using the legacy in-memory route.
- KG reconciles stable FDA application/submission event identity and stores
  source-record versions, source-fact observations, source-fact claims,
  supporting evidence, temporal history, and transactional outbox updates.
- Exact unique FDA product-number matches may link events to canonical
  assets. No name-only sponsor/product association is inferred.
- The implemented regulator is FDA Drugs@FDA only. Broader regulatory
  authorities, FDA labeling/safety sources, distributed rate coordination,
  and structured OpenSearch facets remain documented limitations.
- Implementation, API surfaces, test results, and closure gaps are recorded
  in `PHASE_7_IMPLEMENTATION.md`.

## Phase 8 — IP & Licensing Intelligence (Complete With Documented Limitation)

- The Literature owner adds a rate-limited Google Patents XHR adapter to the
  existing durable job/checkpoint/retry/dead-letter system. Current patent
  rows and content-hashed response snapshots are tenant-scoped and idempotent.
- KG adds canonical patent-family and licensing-event entity types, namespaced
  patent/family/event identity, source-backed patent-family membership,
  append-only source-fact observations, source-fact claims, supporting
  evidence, temporal history, and transactional outbox updates.
- Patent identifiers and source-provided date precision are retained without
  fabricating exact publication instants. Applicant, assignee, and inventor
  values remain distinct; parties are linked only by a unique exact
  namespaced identifier.
- Structured licensing/assignment events support territory, field/rights
  scope, effective/expiry date strings, and explicit `unknown` exclusivity.
  No name-only ownership association or legal/FTO conclusion is generated.
- Google Patents is the only automated patent source. Official office
  assignment feeds, automated licensing-disclosure acquisition/extraction,
  broader family normalization, and dedicated search facets are documented
  limitations. Results are in `PHASE_8_IMPLEMENTATION.md`.

## Phase closure state

Phase 2 remains closed. Phase 3 remains closed. Phase 4 remains closed with
its documented limitation. Phase 5 remains closed with the source-set
stability, distributed rate-coordination, and temporal representation
limitations recorded above. Phase 6 is complete with the study-text
entity-linking limitation documented above and in
`PHASE_6_IMPLEMENTATION.md`. Phase 7 is complete with the regulator/source
coverage, offset-window, OpenSearch facet, and distributed rate-coordination
limitations documented in `PHASE_7_IMPLEMENTATION.md`.
Phase 8 is complete with documented Google Patents coverage, external
availability, licensing-disclosure acquisition, authoritative assignment
history, legal/FTO, and dedicated facet limitations in
`PHASE_8_IMPLEMENTATION.md`. Phase 2, 3, 4, 5, 6, and 7 remain closed.
**Next phase: Phase 9 — Search & Retrieval.**