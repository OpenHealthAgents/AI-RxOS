# Phase 15 — Monitoring and Human Review

## Prompt 69 — Continuous Monitoring

**Status: Prompt 69 — COMPLETE WITH DOCUMENTED LIMITATION**

The repository implements durable material-change monitoring in the existing
Literature ingestion path, including source snapshots, event tracking,
exact tenant scoping, and decision-recalculation records when the supported
Decision Engine is available. The implementation is complete in repository-local
scope and validated by the Literature monitoring tests, but it is still limited
by the repository's live PostgreSQL/RLS dependencies and by the fact that
several monitoring domains are intentionally unsupported in the current source
ingestion pipeline. Existing Prompt 67 and Prompt 68 statuses remain recorded in
[PHASE_14_IMPLEMENTATION.md](./PHASE_14_IMPLEMENTATION.md) and are not changed by
this document.

### Implemented monitoring domains

Monitoring is connected to the existing persisted Literature upserts for:

| Domain            | Source                 | Ingestion path                                                 |
| ----------------- | ---------------------- | -------------------------------------------------------------- |
| Publications      | PubMed                 | `services/literature/app/services/pubmed_ingestion.py`         |
| Clinical trials   | ClinicalTrials.gov     | `services/literature/app/services/clinicaltrials_ingestion.py` |
| Regulatory events | Regulatory/FDA records | `services/literature/app/services/regulatory_ingestion.py`     |
| Patents           | Patent records         | `services/literature/app/services/patent_ingestion.py`         |

Company events, licensing, competitors, resistance evidence, and CNS evidence
do not have corresponding persisted source integrations in this Literature
pipeline. The monitoring source mapper rejects those domains rather than
presenting them as operational.

### Change detection and version history

- `services/literature/app/monitoring/change_detection.py` selects
  source-specific material fields, removes known retrieval/transport
  metadata, serializes deterministically, and computes SHA-256 content
  digests. Nested mappings are compared into stable field paths; lists are
  compared as values.
- `services/literature/app/database/postgres.py` stores raw source snapshots
  with material hashes and payloads. Identical source and material versions
  are deduplicated. A changed source version is retained even if selected
  material fields are unchanged; it does not emit a material-change event.
- Changes to material fields create an event that links the immediately
  preceding and current snapshot. Returning to content seen earlier remains
  a new transition because each material transition uses its own snapshot.
- Event UUIDv5 identity incorporates source, source identity, tenant scope,
  and the two persisted snapshot IDs. Repeating an already-current identical
  content/material version is a no-op. A new transition, including a
  reversion, receives its own event identity.
- Source event time is parsed from a source publication/update/effective date
  when available. `detected_at` uses PostgreSQL `clock_timestamp()` at event
  insertion, so it is distinct from source time and caller-supplied retrieval
  time. Unparseable source dates remain null.
- Snapshots and events are written inside the existing Literature PostgreSQL
  transaction used for the corresponding source-record upsert. Failures
  propagate and roll back that transaction; existing ingestion job
  checkpoint/retry/dead-letter behavior remains responsible for recovery.
  Monitoring does not add a separate job queue or checkpoint mechanism.

### Tenant security and API

- `GET /api/v1/monitoring/events` is registered by
  `services/literature/app/main.py`. It uses the existing trusted
  `get_tenant_context`; no caller-provided tenant parameter controls scope.
- The database query explicitly filters exact tenant equality (including
  global/null scope) in addition to relying on the existing Literature RLS
  context. Event data includes snapshot references, not a cross-tenant
  snapshot retrieval endpoint.
- The API reports HTTP 503 when the PostgreSQL-backed event store is
  unavailable; it does not return a success-shaped empty result.
- Automated tests verify trusted tenant context and assert that the database
  query is tenant-filtered. Actual cross-tenant RLS behavior still requires
  the configured PostgreSQL integration database.

### Canonical evidence and decision recalculation

- Existing ingestion and reconciliation code remains responsible for
  canonical integration. Events retain source snapshot references and are
  updated with canonical resolution outcomes where the existing
  reconciliation path supplies them. Unresolved identity stays explicitly
  `unresolved`.
- The repository implements the Prompt 69 decision-recalculation path in the
  Literature PostgreSQL manager: when a material change is detected for a
  supported source category, the system derives a decision signal payload,
  evaluates the repository's decision engine, stores the previous/current
  decision version, and records whether the decision changed. This is a
  repository-local implementation and not a full enterprise decision-replay
  system.
- Unsupported monitoring domains (company/licensing, competitor, CNS, and
  resistance sources) are intentionally not represented as operational in the
  current Literature pipeline, and the implementation does not fabricate a
  decision-change result for a source that has no persisted identity or engine
  binding.
- There is no separate material-change worker beyond the source-ingestion
  transaction, so downstream feature/prediction/decision processing failures
  remain handled by the ingestion transaction and existing retry logic rather
  than a dedicated asynchronous replay pipeline.

### Validation evidence

Commands below were run from the repository root, with the Literature
directory selected as specified:

```powershell
Set-Location services\literature
& ..\..\.venv-1\Scripts\python.exe -m pytest -q -rs tests\test_continuous_monitoring.py tests\test_pubmed_persistence.py
```

Result: **18 passed, 6 skipped**. All six skips are PostgreSQL persistence
tests; `tests\test_pubmed_persistence.py` requires
`LITERATURE_TEST_DATABASE_URL` and `LITERATURE_TEST_MIGRATION_DATABASE_URL`
(with the documented KG test URL fallbacks). These skips do not count as
passes. The focused tests exercise supported/unsupported source mapping,
material hashing and changed fields, deterministic transition IDs, tenant
API context, and exact tenant filtering in the persistence query. Runtime
snapshot/event transactions and RLS were not exercised without the test
databases.

```powershell
& ..\..\.venv-1\Scripts\python.exe -m compileall -q app
```

Result: **passed**.

```powershell
& ..\..\.venv-1\Scripts\python.exe -m pytest -q -rs tests
```

Result: **160 passed, 7 skipped**. Six skips are the Literature
PostgreSQL-backed persistence tests described above. One skip is the legacy
tenant-enforcement test, which requires `KG_TEST_DATABASE_URL`. The full
suite passed on the changed service, but those skips leave live database/RLS
validation unproven.

From the repository root:

```powershell
pnpm exec prettier --check docs/PHASE_15_IMPLEMENTATION.md
git diff --check
```

Prettier check: **passed**. `git diff --check`: **passed**. Git emitted
working-copy line-ending conversion warnings for unrelated dirty files.

### Prompt 70 — Human Scientific Review

**Status: Prompt 70 — COMPLETE**

The repository did not include a durable human-review workflow, so Prompt 70 was
implemented as a narrow compatibility layer within the existing
`apps/ai-services` opportunity-engine architecture. It reuses the current
request-scoped tenant and user context, preserves the original AI output in
separate review records, and records human actions with rationale, reviewer,
review timestamp, model and evidence version linkage, and tenant scope.

#### Implemented review actions

- Evidence approval: `approve_evidence()` persists an approval record without
  mutating the original evidence or AI claim.
- Evidence rejection: `reject_evidence()` records a rejection while retaining the
  original evidence and provenance.
- Entity correction: `correct_entity()` stores the original resolution and the
  corrected canonical entity separately; it validates that the target entity is
  a known accessible asset in the existing fixture catalog.
- Classification correction: `correct_classification()` preserves the original
  classification and stores the corrected label and rationale separately.
- Human evidence submission: `add_evidence()` accepts provenance-backed evidence
  payloads and preserves their original source/provenance metadata.
- Evidence-quality change: `change_evidence_quality()` preserves the previous
  assessment and records the new value with rationale and reviewer identity.
- Prediction review: `review_prediction()` references the exact prediction and
  maintains a separate review record rather than overwriting the prediction.
- Recommendation override: `override_recommendation()` preserves the original AI
  recommendation and stores a human disposition separately; downstream callers can
  distinguish AI recommendation from human-reviewed disposition.

#### Persistence and API

The implementation adds `apps/ai-services/app/opportunity_engine/review/` with
Pydantic models and in-memory review persistence. The service records the exact
reviewed object, action, status, original AI value, human decision, rationale,
reviewer identity, tenant scope, model version, evidence version, and idempotency
key. The API endpoints are registered in `app.main`, and each route requires a
trusted request `tenant_id` and `user_id` from the authenticated request state.
Client-supplied `reviewer_user_id` values are rejected if they differ from the
trusted session identity.

#### AI preservation guarantees

- Original AI output remains unchanged in the source record, prediction, or
  recommendation object.
- Review records are append-only and separate from the underlying AI decision.
- Rejection does not delete evidence or historical observations.
- Overrides are stored as human-reviewed dispositions rather than replacements of
  the AI recommendation.
- Missing versions remain `None` instead of being fabricated.

#### Focused validation

Commands run:

```powershell
Set-Location apps\ai-services
..\..\.venv-1\Scripts\python.exe -m pytest -q tests\test_human_scientific_review.py tests\test_master_decision_engine.py
```

Result: **18 passed**.

Compilation check:

```powershell
Set-Location apps\ai-services
..\..\.venv-1\Scripts\python.exe -m compileall -q app
```

Result: **passed**.

`git diff --check` was run from the repository root after the Prompt 70 changes.
Result: **passed**.

#### Remaining work

Prompt 69 remains incomplete until the supported integrations are validated
against the disposable PostgreSQL test databases and the repository provides
the missing historical decision/recalculation/explanation path. Additional
unimplemented monitoring domains are company events, licensing, competitors,
resistance, and CNS. No external source, deployed integration, or production
database was used for validation in this task. Prompt 70 was implemented and
validated in the existing AI-services codepath; Prompt 71 was not started.
