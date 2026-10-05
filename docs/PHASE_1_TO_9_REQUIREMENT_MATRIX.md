# PHASE 1–9 REQUIREMENT MATRIX

This matrix records the latest local execution evidence. A PASS indicates the stated repository-controlled behavior was exercised; it does not establish production, external-source, or legal certification. The decision is recorded in [final certification](./PHASE_1_TO_9_FINAL_CERTIFICATION.md), with workspace check details in [final verification](./PHASE_1_TO_9_FINAL_VERIFICATION.md). Phase 10 has not started.

| Phase | Requirement ID | Requirement | Implementation | Runtime path | Persistence | API | Tests | Security / tenant | Status |
|---|---|---|---|---|---|---|---|---|---|
| 1 | P1-01 | Monorepo and service layout | Present in repo structure and tooling config | apps/services packages compose | N/A | N/A | Repo structure inspected | Multi-service boundary exists | PASS |
| 1 | P1-02 | Gateway/auth foundation | Go gateway + auth service present | auth + gateway paths | Postgres and Redis config present | Gateway routes and auth code exist | Service-specific validation exercised | Auth paths exist | PASS |
| 1 | P1-03 | Observability and deployment config | Docker/Helm manifests present | docker-compose.yml + infra/helm | Config manifests present | Service health paths exist | Not full live stack validation | Service-level security config exists | PARTIAL |
| 2 | P2-01 | Canonical entities and identities | KG canonical models and identifiers present | kg service + search projection | PostgreSQL + Neo4j + OpenSearch path exists | APIs and search integration exist | Search tests + KG tests passed | Tenant filters exist | PASS |
| 2 | P2-02 | Provenance and source-record model | Source-record / observation logic present | literature + kg integration | Source snapshot persistence present | API and service integration present | KG + literature suites passed | Tenant scoping present | PASS |
| 2 | P2-03 | Outbox / projection path | Outbox and projection code exists | kg -> search path | Postgres outbox and indexer path exists | Search consumer surfaces | Search tests passed | Search tenant filtering checked | PASS |
| 3 | P3-01 | Evidence lineage | Claims + evidence links implemented | literature + kg plus canonical model | DB-backed evidence model | API + service present | KG tests passed | Evidence isolation paths present | PASS |
| 3 | P3-02 | Contradicting/supporting evidence | Evidence polarity and lineage features exist in code and tests | canonical evidence flows | persistent evidence tables | service and API handlers exist | tests executed in KG/literature paths | tenant isolation present | PASS |
| 4 | P4-01 | Temporal semantics | knowledge_available_at + superseded_at in search, as-of filtering present | search projection and query path | OpenSearch fields persist temporal state | search API supports as_of | Search tests passed | time bounds kept | PASS |
| 4 | P4-02 | Future leakage prevention | as-of logic present | search and canonical filtering | temporal fields in data model | query-level filter via as_of | Search tests cover temporal and tenant behavior | correct scoping inside query path | PASS |
| 5 | P5-01 | PubMed voluntary ingestion | NCBI connector and literature pipeline present | services/literature connectors | raw snapshot + literature persistence | ingestion service + jobs | Literature suite passed | tenant-scoped ingestion jobs present | PASS |
| 5 | P5-02 | Retry / checkpoint / dead-letter | job checkpoint and retries coded | literature job system | Postgres job state and logs | service APIs exist | literature tests passed | tenant filters and fail-close patterns present | PASS |
| 6 | P6-01 | ClinicalTrials ingestion | literature service contains trial ingestion pathways | literature/clinicaltrials adapters | durable records and snapshots | service and API paths present | included in literature suite | tenant scoping in job system | PASS |
| 6 | P6-02 | Retry, pagination, restart semantics | page-token / retry logic present | ingestion job system | queue/job state persisted | service APIs exist | deterministic tests passed | tenant-safe flow present | PASS |
| 7 | P7-01 | Regulatory intelligence core model | regulatory/integration infrastructure present | literature + kg service paths | source snapshot/provenance storage present | API/service integrations present | not full live-source suite | tenant scoping exists | PARTIAL |
| 7 | P7-02 | Real regulatory source validation | live integration requires official source credentials / environment | not verified end-to-end in this session | not fully validated | live API gateway not exercised | live/regulatory suite not run | external dependency risk | UNVERIFIED |
| 8 | P8-01 | IP / licensing foundation | patent/licensing model present in research/service code | kg + literature layers | persistence present in canonical model | service+API code exists | not exhaustive live validation | tenant scoping present | PARTIAL |
| 8 | P8-02 | Legal safety / provenance | evidence lineage and uncertainty semantics coded | source-to-evidence flow | versioned source records and evidence | service/API path exists | not full live validation | requires legal-safe semantics | PARTIAL |
| 9 | P9-01 | Search service build and tests | Go search service implemented | search service runtime | per-tenant OpenSearch queries | handler APIs present | Search tests passed | tenant filters enforced | PASS |
| 9 | P9-02 | Search API and hybrid retrieval | keyword + semantic + hybrid logic present | search service + handlers | OpenSearch + vector index queries | handlers and stream API present | unit tests passed | tenant filtering validated | PASS |
| 9 | P9-03 | Local integration-stack validation | PostgreSQL, Neo4j, Search, and Redis were available locally | B10 exercised source → PostgreSQL/outbox → Neo4j/Search | tenant-scoped B10 and Auth RLS tests passed | local Search and KG API paths exercised | KG 100 passed; Auth 62 passed; Search Go tests passed | tenant isolation exercised | PASS (local stack only) |

## Audit status summary

- Phase 1: PARTIAL (auth/runtime tests passed; full deployment/observability certification not performed)
- Phase 2: PASS for executed canonical data, outbox, projection, and tenant tests; static checks still fail
- Phase 3: PASS for executed evidence-lineage test paths; static checks still fail
- Phase 4: PASS for executed temporal/search test paths
- Phase 5: PASS for executed literature tests; 42 mypy and 32 Ruff findings remain
- Phase 6: PASS for executed ClinicalTrials/integration tests; static checks still fail
- Phase 7: PARTIAL / UNVERIFIED (live regulatory integrations and full external validation not proven here)
- Phase 8: PARTIAL / UNVERIFIED (IP/licensing implementation exists but not fully proven end-to-end)
- Phase 9: PASS for local integration-stack runtime tests; production deployment remains unverified

Overall conclusion: **NOT CERTIFIED.** Local runtime/integration tests passed, but KG/Literature typecheck and lint failures, Windows standalone-build symlink errors, a Storybook type error, and unverified live regulatory/IP requirements remain. See [final verification](./PHASE_1_TO_9_FINAL_VERIFICATION.md) for the recorded test and check results. Phase 10 has not started.
