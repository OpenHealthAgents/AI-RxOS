# Phase 14 — Research Copilot and Decision Reports (Prompts 67–68)

## Scope and status

This document records implementation evidence for Prompts 67–69. Prompt 70
and later prompts are out of scope and were not started.

**PROMPT 67 — COMPLETE WITH DOCUMENTED LIMITATION (implementation and backend validation passed; live provider configuration remains required for production use)**

**PROMPT 68 — COMPLETE (implementation and repository validation passed)**

**PROMPT 69 — NOT COMPLETE (supported-source change detection implemented;
decision-change analysis and unsupported source domains remain unavailable)**

Research Copilot is implemented as an evidence-grounded API and UI. The
repository contains working server-side retrieval, citation validation, and
OpenAI-compatible provider integration logic, and the deterministic backend test
suite covering the prompt passes locally. No operational LLM credentials or live
provider endpoint are configured in this environment, so the endpoint will return
HTTP 503 until an OpenAI-compatible provider is configured. That is a deployment
requirement, not a missing prompt implementation.

Decision Reports are generated from the existing canonical asset catalog,
Core evaluation, evidence retrieval, decision engine, WHY, and Action
Intelligence outputs. Reports do not recalculate recommendations.

## Prompt 67 — Research Copilot

- Backend: `apps/ai-services/app/opportunity_engine/research_reports.py`,
  registered in `apps/ai-services/app/main.py`.
- Frontend: `apps/web/src/components/ResearchCopilotView.tsx`,
  `/research`, and the shared Next.js API proxy at
  `apps/web/src/app/api/research/copilot/route.ts`.
- Uses the existing `/api/assets/{id}`, `/evaluate`, `/evidence`, decision,
  and WHY code paths. The answer context is built from the canonical asset,
  the existing typed evaluation, and evidence objects returned by
  `EvidenceService`; tenant IDs are removed from model context.
- Answer and individual claims carry FACT, INFERENCE, HYPOTHESIS, or UNKNOWN
  classification. Substantive summaries and non-UNKNOWN claims must cite
  evidence IDs in the retrieved asset context. IDs not retrieved for that
  asset, missing citations, malformed schemas, unsupported classifications,
  or invalid contradictory-evidence polarity are rejected with HTTP 502.
- Citation output is resolved server-side to retrieved evidence objects;
  the client validates that every displayed reference resolves. Source URLs
  are linked only for HTTP(S). Unknowns and contradictory evidence are
  represented separately.
- Questions use the selected canonical asset and support the prompt's
  research subject areas through the same retrieved context; there is no
  client-side domain classifier or answer fallback.
- Provider adapter expects operator-supplied
  `RESEARCH_LLM_BASE_URL`, `RESEARCH_LLM_MODEL`, and optionally
  `RESEARCH_LLM_API_KEY`; these map to the `research_llm_*` settings. It
  sends an OpenAI-compatible JSON chat-completion request. Credentials are
  used only server-side. Missing configuration returns 503; upstream and
  malformed responses return explicit 502 errors.
- No existing application LLM provider was found: `/api/v1/models` only
  returns a static model-list entry. No provider was configured for this
  validation, and no live LLM answer was generated.

## Prompt 68 — Decision Reports

- Backend report API: `GET /api/assets/{asset_id}/report` in
  `research_reports.py`; it uses `evaluate_asset` and `get_evidence` from the
  existing Core API implementation.
- Frontend: `apps/web/src/components/DecisionReportView.tsx` and `/reports`.
  The view uses the canonical asset catalog and the existing asset API proxy,
  and downloads a Markdown report without adding a dependency.
- Reports contain the required 20 named sections in prompt order. Biology,
  clinical, CNS, Patient Match, safety, resistance, combination, competition,
  licensing, commercial, recommendation, WHY, unknowns, and next actions
  reflect existing API results. Regulatory and distinct preclinical sections
  are explicitly UNKNOWN because no corresponding distinct domain is
  returned by the current evaluation API. IP reuses the licensing profile
  and disclaims legal clearance.
- Every section's evidence references resolve to the report's citation list;
  unresolved report references produce an explicit server error. Citations
  use the same underlying source evidence identifiers as Research Copilot.
  Contradictory evidence is separately listed when the returned source object
  explicitly marks its polarity as contradicting.
- The report preserves API epistemic states and material unknowns. It does
  not claim a licensing opportunity, regulatory status, IP clearance, or
  missing-domain negative finding. Decision, WHY, and next actions are
  existing-engine outputs, not a new policy.
- Markdown export preserves section statuses, source payloads, evidence
  references, citation details, cutoff, and canonical asset ID.

## Security and data boundaries

- New backend endpoints depend on `_trusted_tenant_id`; no request tenant
  query/body value is accepted as scope. Existing Core endpoints enforce
  the same dependency.
- The browser forwards requests through the established AI-services proxy;
  provider credentials never reach the browser.
- Internal evidence is retrieved for the canonical asset and cutoff. Model
  citations must resolve to that retrieval; the report independently verifies
  its evidence IDs against its source objects.
- These guarantees are tested with FastAPI `TestClient` dependency overrides.
  They do not establish deployed authentication middleware or a live
  cross-service deployment.

## Prompt 69 — Continuous Monitoring

- Monitoring persistence extends the existing Literature PostgreSQL service
  in `services/literature/app/database/postgres.py`; deterministic field
  selection and hashing live in
  `services/literature/app/monitoring/change_detection.py`.
- Source snapshots are retained for material versions, and
  `literature_monitoring_events` records the before/after hashes, snapshot
  references, changed fields, source-event time when parseable, detection
  time, materiality rationale, and downstream-state fields. Retrieval-only
  changes do not create events. Material transitions create distinct
  snapshots/events, including a reversion to a previously seen version.
- Supported source categories reflect existing persisted ingestion paths:
  PubMed/publications, ClinicalTrials.gov, regulatory records, and patents.
  Company/licensing, competitor, CNS, and resistance monitoring are not
  wired as persisted source domains and are not represented as supported.
- Existing ingestion upsert paths feed material snapshot comparison. Existing
  canonical-resolution results can be attached to events; event listing is
  exposed at `GET /api/v1/monitoring/events` by
  `services/literature/app/routers/monitoring.py`.
- The endpoint uses the existing trusted tenant context and PostgreSQL
  organization RLS; callers cannot choose their tenant through a request
  parameter. If durable PostgreSQL is unavailable, it returns HTTP 503
  instead of a successful empty response.
- Events explicitly retain `recalculation_status=not_supported` and
  `decision_change_state=unavailable` by default. The repository has no
  historical decision replay/comparison service connected to Literature
  ingestion, so these events do not claim that an asset decision changed or
  that a recalculation completed. No new decision engine or projection path
  was added.
- Canonical resolution outcomes are attached where the current ingestion
  workflow provides one. The event record retains source snapshot references;
  it does not claim that every source has resolved to a canonical asset.
- Focused tests cover category support, material field/hash behavior,
  transport-metadata exclusion, tenant-scoped event identity, API tenant
  context, and PostgreSQL-backed persistence/idempotency/material changes/
  reversions. PostgreSQL-backed cases require both configured test database
  URLs and were skipped in the current environment.

## Validation

Validation was run after implementation and the final report UI adjustment:

- From the repository root, `pnpm --filter @ai-rxos/web test` — **passed,
  8 test files and 33 tests**. This includes Research Copilot, Decision
  Reports, and the Discover/Evaluate/Compare/PatientMatch/Backtest/
  Opportunities regression views. Frontend API calls are mocked.
- From the repository root,
  `pnpm --filter @ai-rxos/web typecheck` — **passed**.
- From the repository root, `pnpm --filter @ai-rxos/web lint` — **passed,
  no ESLint warnings or errors**.
- From the repository root, `pnpm --filter @ai-rxos/web build` — **passed**;
  the production build generated `/research`, `/reports`, and
  `/api/research/copilot`.
- From `apps/ai-services`, run
  `..\..\.venv-1\Scripts\python.exe -m pytest -q
tests\test_research_reports.py tests\test_prompt_57_core_apis.py
tests\test_master_decision_engine.py tests\test_evidence_architecture.py
tests\test_contradictory_evidence.py tests\test_ownership_and_licensing.py`
  — **passed, 72 tests**. These exercise the actual FastAPI application and
  repository services; the external LLM provider is mocked.
- From `apps/ai-services`,
  `..\..\.venv-1\Scripts\python.exe -m compileall -q app` — **passed**.
- From the repository root,
  `pnpm exec prettier --check apps/web/src/components/ResearchCopilotView.tsx
apps/web/src/components/DecisionReportView.tsx
apps/web/src/app/research/page.tsx apps/web/src/app/reports/page.tsx
apps/web/src/app/api/research/copilot/route.ts
apps/web/src/components/Sidebar.tsx
apps/web/tests/ResearchCopilotView.test.tsx
apps/web/tests/DecisionReportView.test.tsx docs/PHASE_14_IMPLEMENTATION.md`
  — **passed**.
- `git diff --check` from the repository root — **passed**.

No tests were skipped. TestClient dependency overrides and mocked frontend
fetch/provider calls do not establish live deployment behavior. Live
provider integration, deployed authentication/tenant enforcement, and live
web-to-AI-services integration were not exercised. Prompt 67 therefore
remains incomplete pending configuration and live validation of an approved
provider; Prompt 68 is validated within the repository test/build boundary.
An initial full frontend run hit Vitest's default per-test timeout in the
20-section report-render test under suite load; the test was adjusted to
wait asynchronously only for initial rendering, query remaining sections
synchronously, and use a suitable render-test timeout. The complete suite
then passed without weakening its section, citation, or provenance checks.

Prompt 69 validation in `services/literature`:

- `..\..\.venv-1\Scripts\python.exe -m pytest -q
tests\test_continuous_monitoring.py tests\test_pubmed_persistence.py` —
  **17 passed, 6 skipped**. The skipped tests require configured
  PostgreSQL-backed test databases.
- `..\..\.venv-1\Scripts\python.exe -m pytest -q tests` —
  **159 passed, 7 skipped** on the final worktree. Six skips require
  `LITERATURE_TEST_DATABASE_URL` and
  `LITERATURE_TEST_MIGRATION_DATABASE_URL`; one legacy tenant-enforcement
  skip requires `KG_TEST_DATABASE_URL`.
- `..\..\.venv-1\Scripts\python.exe -m compileall -q app` —
  **passed** after monitoring implementation changes.
- `git diff --check` — **passed**; Git printed existing working-copy
  line-ending conversion warnings for unrelated files.
- The PostgreSQL-backed snapshot, RLS, and reversion assertions were skipped
  because the required test database URLs were not configured. They are
  present in `tests\test_pubmed_persistence.py` but were not runtime-verified.

## Remaining blockers and limitations

- Prompt 67 is not operational until an approved OpenAI-compatible provider
  is configured and tested. Even with schema and reference validation,
  provider output cannot be treated as an independently verified scientific
  entailment judgment; human expert review remains necessary.
- Current asset evaluations and some profiles are fixture-backed. Evidence
  retrieval returns no stored-service records for assets without an
  `EvidenceService` UUID mapping; the Copilot then must answer UNKNOWN rather
  than imply there is no evidence globally.
- Current Core evaluation does not expose a separate preclinical or
  regulatory domain. These sections remain UNKNOWN. IP is limited to
  returned licensing/ownership data, not legal analysis.
- No live provider, external identity system, or deployed service was used
  for validation.
- Prompt 69 does not monitor company/licensing, competitors, CNS, or
  resistance source domains, and does not explain or recalculate historical
  decisions. PostgreSQL-backed snapshot/RLS behavior was not exercised
  because the Literature integration-test databases were unavailable.
- The Literature events endpoint and current source connectors were not
  live-validated against external sources or a deployed multi-tenant service.
