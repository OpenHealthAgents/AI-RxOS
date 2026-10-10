# Phase 13 — Product Workspaces (Prompts 61–66)

## Scope and status

Phase 13 covers Prompt 61 Discover, Prompt 62 Evaluate, Prompt 63 Compare,
Prompt 64 PatientMatch, Prompt 65 Backtest, and Prompt 66 Opportunities. No
Prompt 67 or later work is included.

This document records Phase 13 implementation and validation; the Phase 11
documentation is unchanged.

**PHASE 13 — COMPLETE (PROMPTS 61–66)**

The six focused workspace tests, full web test suite, web typecheck, web lint,
production build, relevant AI-services tests, Python compile check, changed-
file formatting check, and diff whitespace check pass. Browser tests mock API
requests and backend tests use FastAPI `TestClient`; a live web-to-AI-services
deployment was not exercised. Fixture-backed data and endpoint limitations
remain explicitly disclosed below.

## Prompt 61 — Discover

- `DiscoverView` submits search intent and supported filters to the existing
  Discover API and renders returned interpretation, ranked candidates,
  evidence, confidence, and provenance. It does not create candidate results
  or persist unsupported search state.
- Loading, API error, empty, malformed-response, and partial/unknown states
  are represented explicitly. Candidate navigation uses the canonical API
  asset ID.
- Compare requests use the existing Compare API. Unsupported actions are not
  implied by the Discover result.

## Prompt 62 — Evaluate

- `EvaluateView` loads canonical assets and uses the existing Core asset,
  evaluation, evidence, history, and WHY APIs. An asset must be selected (or
  supplied canonically through navigation) before it is evaluated.
- Recommendation, priority, score, confidence, domain availability,
  supporting and contradictory evidence, unknowns, cutoff, policy/model/
  feature provenance, and backend WHY data are rendered from API responses;
  the browser does not recalculate a decision.
- Missing domains remain unknown/unavailable, not negative evidence.
  Malformed required responses surface as errors, optional evidence/history
  failures are reported separately, and only HTTP(S) evidence URLs are linked.
- Categories or explanations not returned by the backend are identified as
  unavailable rather than inferred.

## Prompt 63 — Compare

- `CompareView` submits selected canonical asset IDs and an optional cutoff
  with `POST /api/compare`.
- The Next.js route forwards the request through the shared AI-services proxy
  to `POST /api/compare`; the FastAPI endpoint validates the request and
  returns backend-computed outcomes.
- The browser renders the API's winner status, winner ID, confidence,
  per-asset metrics, evidence, provenance, contradictions, and unknowns. It
  does not calculate comparative scores or choose a winner.
- Missing or asymmetric evidence remains explicitly unknown or insufficient;
  it is not treated as negative evidence.

## Prompt 64 — PatientMatch

- `PatientMatchView` submits the existing cohort scenario request and retrieves
  each returned candidate's PatientMatch intelligence through the existing
  APIs.
- Backend-provided ranks and scores are displayed without browser-side
  re-ranking or recommendations. Population values, evidence, epistemic
  states, confidence state, uncertainty, model and feature versions, and
  provenance are rendered when returned. Evidence metadata is available
  alongside its readable citation.
- The current PatientMatch intelligence contract does not return a
  contradiction collection. The UI says that explicitly; absence is not
  presented as evidence that there are no contradictions. Any
  `contradictory_evidence` field returned by the API is preserved and shown.
- The existing scenario matcher accepts expression, amplification, protein
  expression, line-of-therapy, and CNS-status fields, but does not use them as
  separate matching inputs. The form discloses this limitation; the client
  does not claim those fields affect ranks or scores.
- The scenario endpoint uses deterministic keyword rules over a fixed
  benchmark candidate set. Returned ranks and heuristic match scores are not
  calibrated or clinically validated predictions; the UI discloses this
  limitation. This workspace presents cohort/population analysis, not an
  individual treatment recommendation.
- Requests pass through the shared proxy. No client-supplied tenant ID is
  introduced.
- The direct PatientMatch intelligence API reads tenant scope from trusted
  request state instead of a `tenant_id` query parameter. This uses the shared
  request-context dependency also imported by Core, Compare, and Backtest.

## Prompt 65 — Backtest

- `BacktestView` submits to `POST /api/backtest` through the shared Next.js
  proxy route.
- Outcome type options mirror the API's `OutcomeType` values and are sent only
  when selected.
- Stored predictions and cutoff-time feature lineage remain in a separate
  “Known at cutoff” section from outcomes learned later.
- The UI displays backend metric states and unknowns without calculating
  historical predictions or substituting missing metrics. Sensitivity output
  remains labeled hypothetical.

## Prompt 66 — Opportunities

- The workspace loads canonical assets through the existing `/api/assets`
  path and retrieves each asset's existing Core evaluation from
  `/api/assets/{id}/evaluate`. It does not maintain a local asset catalog or
  construct a second decision engine.
- The Core evaluation response now includes an additive typed
  `action_intelligence` result. The existing Action Intelligence engine ranks
  actions server-side from the same decision and WHY result already computed
  for that evaluation. No new endpoint or client-built `DecisionRequest` was
  added.
- Category mapping is deliberately limited to API-supported information:
  `PURSUE`, `PARTNER`, `LICENSE`, `MONITOR`, and `AVOID` map to their matching
  display categories. `Academic` is added only when the ownership profile
  returns `academic_origin`. Unsupported and insufficient-evidence decisions
  remain `Unclassified`. The current focal-asset API does not identify assets
  as `Emerging Threat`; the UI discloses that limitation instead of inferring
  a category from threats to the asset.
- A `LICENSE` decision and the licensing-domain response state are kept
  separate from the profile's `licensing_status` value. The UI only describes
  availability as verified when the profile returns the verified state and
  its verification source. Ownership names are labeled as catalog/profile-
  reported, not identity-verified; no sponsor is inferred.
- Decision score and confidence, decision and WHY evidence, contradictions,
  unknowns, evidence gaps, evaluation cutoff, decision policy, model versions,
  and feature versions are preserved as returned. Unknown values remain
  unknown. Decision and WHY uncertainty are combined without discarding
  either source.
- The workspace displays the first already-ranked Prompt 56 action and its
  returned rationale, priority, metrics, evidence, unknowns, and lineage. It
  does not sort or score actions in the browser, create tasks, or claim that a
  suggestion has been executed.
- The WHY explanation is presented as decision context. The current API
  provides no time-sensitive trigger, so the UI states that none was returned
  and does not infer urgency or an event.
- Contract review distinguished `licensing.status` (whether the domain data
  response is available) from `licensing.data.licensing_status` (the profile's
  licensing assertion). They are now rendered separately, preventing an
  `AVAILABLE` domain response from being presented as available rights.
- Evaluate navigation passes the canonical asset ID. Compare navigation
  preselects that one canonical asset and leaves counterpart selection to the
  user. No-query Compare defaults and legacy two-canonical-ID query
  preselection remain supported.

## API, authentication, and tenant handling

- The web routes use the shared AI-services proxy, which forwards the
  incoming authorization, cookie, and content-type headers and returns
  upstream status and response content. Upstream connection failures are
  logged and returned as explicit HTTP 502 responses.
- Compare, Backtest, and the PatientMatch intelligence endpoint use the
  existing trusted tenant dependency in the AI services. The PatientMatch
  endpoint ignores caller-supplied `tenant_id` query parameters. The browser
  does not submit a tenant identifier.
- Discover saved-search tenant isolation and PatientMatch trusted-context
  behavior have backend test coverage. PatientMatch scenario matching uses a
  fixed public benchmark profile set; it is not tenant-specific patient
  population storage.
- Request validation and domain errors remain in the existing FastAPI routes;
  the proxy does not introduce a parallel backend or decision engine.
- Opportunities uses those same authenticated asset/evaluation routes. The
  additive Action Intelligence result reuses the Core API's trusted tenant
  dependency and carries no client-supplied tenant identifier.
- Proxy/header forwarding and backend tenant boundaries were inspected and
  tested at the route level. External identity-provider configuration and
  deployed authentication/authorization behavior were not live-tested.

## Prompt 61–62 regression audit

- Discover and Evaluate now validate successful API payload shapes before
  rendering. Malformed responses surface as errors rather than success-shaped
  fallbacks; absent Evaluate domains are labeled unknown with the API reason.
- Evaluate keeps decision, evidence, unknown, and model provenance fields
  distinct, exposes returned provenance, and only renders HTTP(S) evidence
  URLs as links. A tenant value not returned by the API is shown as unknown.
- Regression tests cover malformed API responses, partial domains, evidence
  links, and model provenance. Existing Prompt 61/62 user flows remain intact.

## Failure recovery and fixes

The resumed focused frontend run reported three test assertion failures:

1. Compare expected an exact standalone `NOT COMPARABLE` text node, while the
   view renders the API outcome inside its labeled outcome paragraph. The
   test now asserts the labeled backend result.
2. PatientMatch queried `AVAILABLE` without scoping the query, while both the
   population and model states rendered it. The test now checks each labeled
   state independently.
3. Backtest expected `INSUFFICIENT LABELS`, while the API's exact state is
   `INSUFFICIENT_LABELS`. The test now asserts the API enum and allows repeated
   metric states.

The initial typecheck reported `TS2571: Object is of type 'unknown'` in
`EvaluateView.tsx` while formatting a confidence value from a
`Record<string, unknown>`. The value is now read into a local and narrowed
with `typeof confidence === "number"` before formatting. Decision extraction
is memoized to avoid an unstable hook dependency. A later typecheck also found
`TS2532` in a newly added malformed-confidence test because its candidate
fixture is an optional array element; an explicit fixture guard resolves it.

Contract review also found that the Backtest form exposed outcome type as a
read-only field with an instruction placeholder. It now uses the supported
backend enum options and includes the selected value in the POST payload. The
test fixture now uses the API enum value `trial_readout`, not the unsupported
`RESPONSE` value.

An initial `pnpm exec vitest` invocation printed test results followed by a
`Command "vitest" not found` pnpm diagnostic. The package-filtered commands
and established `test` script ran successfully afterward. Vitest was present;
no dependency was missing or installed.

An additional provenance assertion initially expected a formatted JSON
substring in the evidence citation text. The API reports evidence and metric
provenance as separate fields, so the test now verifies the evidence metadata
and the distinct metric provenance output independently. The final focused
tests pass.

A full test run overlapped with lint and exceeded test timeouts; the
uncontended standard web test command subsequently passed all 20 tests.
A typecheck overlapped with an earlier build and reported missing generated
`.next/types` files; it passed when rerun after the build completed.

The first package-wide lint/build attempt exposed four JSX
`react/no-unescaped-entities` errors in evidence excerpts and four
`no-explicit-any` warnings in RadarChart metric access (fatal with
`--max-warnings 0`). JSX quotes are now escaped and metric indexing uses the
existing `BiologyProfileMetrics` keys. Package-wide lint and build now pass.

While changing the direct PatientMatch intelligence endpoint to trusted
tenant context, the first implementation imported the dependency from
`core_api.py`, which imports the PatientMatch router and caused a Python
circular import during test collection. The shared dependency now lives in
`request_context.py`; Core re-exports the imported symbol for existing
callers, and a regression test proves a caller-supplied query tenant cannot
override the trusted tenant.

The final audit also found and fixed two UI issues: Opportunities now rejects
an evaluation response whose canonical `asset_id` differs from the requested
asset, and its licensing copy no longer treats a domain-level `AVAILABLE`
response as proof of licensing rights without the required verification
assertion. The Opportunities test fixtures now return the requested canonical
IDs and include a mismatched-ID regression case. PatientMatch now discloses
that the current scenario engine is deterministic and fixed-benchmark, and
labels its rank and score as backend rule-based/heuristic outputs.

One full-suite run failed because an Evaluate test expected an asset heading
before selecting an asset when no canonical ID was supplied. The production
workspace intentionally waits for an explicit selection in that state; the
test now selects the returned canonical asset before asserting the evaluated
workspace. The corrected test passes without changing that behavior.

## Validation

The final audit commands and results were:

| Command                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Result                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `pnpm --filter @ai-rxos/web test -- tests/DiscoverView.test.tsx tests/EvaluateView.test.tsx tests/CompareView.test.tsx tests/PatientMatchView.test.tsx tests/BacktestView.test.tsx tests/OpportunitiesView.test.tsx`                                                                                                                                                                                                                                                            | Passed — 6 files, 29 tests.                                                                            |
| `pnpm --filter @ai-rxos/web test`                                                                                                                                                                                                                                                                                                                                                                                                                                               | Passed — complete suite, 6 files, 29 tests.                                                            |
| `pnpm --filter @ai-rxos/web typecheck`                                                                                                                                                                                                                                                                                                                                                                                                                                          | Passed — `tsc --noEmit`.                                                                               |
| `pnpm --filter @ai-rxos/web lint`                                                                                                                                                                                                                                                                                                                                                                                                                                               | Passed — no warnings or errors.                                                                        |
| `pnpm --filter @ai-rxos/web build`                                                                                                                                                                                                                                                                                                                                                                                                                                              | Passed — production build completed; 17 static pages generated.                                        |
| `Set-Location apps\\ai-services; ..\\..\\.venv-1\\Scripts\\python.exe -m pytest tests\\test_prompt_55_56_intelligence.py tests\\test_prompt_57_core_apis.py tests\\test_prompt_58_discover_api.py tests\\test_prompt_59_compare_api.py tests\\test_prompt_60_backtest_api.py tests\\test_prompt_64_patient_match_tenant.py tests\\test_patient_match_engine.py tests\\test_opportunity_engine.py tests\\test_discover_engine.py tests\\test_prompt_47_48_49_intelligence.py -q` | Passed — 115 tests.                                                                                    |
| `Set-Location apps\\ai-services; ..\\..\\.venv-1\\Scripts\\python.exe -m compileall -q app`                                                                                                                                                                                                                                                                                                                                                                                     | Passed.                                                                                                |
| `pnpm exec prettier --check` on Phase 13 web source/test globs, `apps/web/package.json`, and this document (exact invocation below)                                                                                                                                                                                                                                                                                                                                             | Passed — all matched Phase 13 source, test, manifest, and documentation files use Prettier formatting. |
| `git diff --check`                                                                                                                                                                                                                                                                                                                                                                                                                                                              | Passed.                                                                                                |

The successful formatting command was:

```text
pnpm exec prettier --check "apps/web/src/app/{backtest,compare,discover,evaluate,opportunities,patient-match}/page.tsx" "apps/web/src/app/api/{assets,backtest,compare,discover,patient-match}/**/*.ts" "apps/web/src/components/{AppShell,BacktestView,CompareView,DiscoverView,EvaluateView,EvidenceProvenanceModal,OpportunitiesView,PatientMatchView,RadarChart,Sidebar}.tsx" "apps/web/src/lib/{ai-services-proxy,api-client}.ts" "apps/web/tests/*.tsx" apps/web/package.json docs/PHASE_13_IMPLEMENTATION.md
```

The broader exploratory `pnpm exec prettier --check apps/web/src
apps/web/tests docs/PHASE_13_IMPLEMENTATION.md` found 23 unformatted legacy
files outside the Phase 13 changed-file set; they were not reformatted as
unrelated scope. `pnpm-lock.yaml` is package-manager-generated and was left in
pnpm's generated format rather than rewritten by Prettier. Frontend tests mock
browser fetches; backend tests exercise FastAPI routes with `TestClient`.
The proxy routes were inspected and the production build passed, but no live
web-to-AI-services deployment was started. No separate Phase 13 gap matrix
was present under `docs/`.

## Files in the verified Phase 13 surface

- Web views: `apps/web/src/components/DiscoverView.tsx`,
  `EvaluateView.tsx`, `CompareView.tsx`, `PatientMatchView.tsx`,
  `BacktestView.tsx`, and `OpportunitiesView.tsx`.
- Workspace pages: `apps/web/src/app/discover/page.tsx`,
  `evaluate/page.tsx`, `compare/page.tsx`, `patient-match/page.tsx`,
  `backtest/page.tsx`, and `opportunities/page.tsx`.
- API routes and shared client/proxy: `apps/web/src/app/api/compare/route.ts`,
  `backtest/route.ts`, `discover/route.ts`, `patient-match/[...segments]/route.ts`,
  `assets/route.ts`, `assets/[...segments]/route.ts`,
  `apps/web/src/lib/api-client.ts`, and `apps/web/src/lib/ai-services-proxy.ts`.
- Frontend tests: `apps/web/tests/DiscoverView.test.tsx`,
  `EvaluateView.test.tsx`, `CompareView.test.tsx`,
  `PatientMatchView.test.tsx`, `BacktestView.test.tsx`, and
  `OpportunitiesView.test.tsx`.
- AI-services API implementation and tests:
  `apps/ai-services/app/main.py`,
  `apps/ai-services/app/opportunity_engine/compare_api.py`,
  `backtest_api.py`, `core_api.py`, PatientMatch engine/router and related
  `test_prompt_59_compare_api.py`, `test_prompt_60_backtest_api.py`, and
  PatientMatch tests including `test_prompt_64_patient_match_tenant.py`;
  tenant context is shared in `request_context.py`.
- Package-wide build/lint support: `apps/web/src/components/EvidenceProvenanceModal.tsx`
  escapes JSX excerpt quotes; `RadarChart.tsx` uses typed metric keys.

## Remaining limitation

The asset catalog is fixture-backed and the temporal engine uses seeded
outcome records. Backtest scores only eligible stored historical predictions
with compatible evidence-backed labels; it does not generate retrospective
predictions from current asset data. The Opportunities view therefore reflects
the returned catalog and its API-backed evaluations, not a complete external
market scan. The API and UI disclose that this is an integration workflow,
not a validated real-world ML benchmark. The current API also has no dedicated
time-sensitive WHY trigger, verified identity status for owner names, sponsor
field, or focal-asset Emerging Threat category. No workflow assignment or
task is persisted, and no live web-to-AI-services deployment was exercised.
