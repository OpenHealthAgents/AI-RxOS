# ai-services

Part of the AI-RxOS platform. See `/architecture` at the repo root for the
full service contract this implements. Runs on port **8090**.

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8090
```

## ML explanations and monitoring

Prediction explanations are available at
`GET /api/v1/ml/predictions/{prediction_id}/explanation` (pass `tenant_id` for a
tenant-scoped prediction). They use the prediction's saved input snapshot and
registered model version. Random forest and gradient-boosting explanations use
instance-specific tree-path contributions; global feature importance is shown
only as separate context. Logistic-regression contributions are expressed in
log-odds. An explanation describes model behavior, not scientific evidence;
any evidence references shown are provenance for derived input features.

`POST /api/v1/ml/monitoring/evaluate` evaluates one registered `model_version`,
one compatible `feature_version`, a tenant scope, and a timezone-aware monitoring
window. It reports prediction/failure volumes, latency and output distributions,
feature PSI and missingness changes, and outcome-based performance/calibration
only when enough temporally valid outcomes are available. Drift alerts are
threshold-backed; missing reference/current populations and insufficient
outcomes are reported as unavailable rather than as zero drift or performance.
Reports are retained in the existing prediction store and can be retrieved with
`GET /api/v1/ml/monitoring/reports/{report_id}` using the same `tenant_id` scope.
The legacy `POST /api/v1/ml/drift/evaluate` endpoint compares its supplied
current data (or saved production snapshots) with the registered model's
training reference.

## Cutoff-aware domain intelligence

The Biology, Clinical, and CNS engines expose synthesized snapshots at
`GET /api/v1/biology/intelligence/{asset_id}`,
`GET /api/v1/clinical/intelligence/{asset_id}`, and
`GET /api/v1/cns/intelligence/{asset_id}`. Each accepts an optional
`prediction_cutoff` date and `tenant_id`. Outputs preserve evidence lineage,
epistemic class, and explicit unknown/unavailable states; undated or
post-cutoff observations are not used as snapshot evidence. Registered ML is
served only when a tenant-visible model and complete point-in-time feature
snapshot are available. CNS measurements, predicted potential, and predicted
activity are represented separately; exposure is not treated as clinical CNS
efficacy.

The related population and resistance synthesis endpoints are
`GET /api/v1/patient-match/intelligence/{asset_id}`,
`GET /api/v1/resistance/intelligence/{asset_id}`, and
`GET /api/v1/combination/intelligence/{asset_id}`. These endpoints accept the
same optional cutoff and tenant parameters. Patient-response and resistance
predictions remain unavailable unless an eligible tenant-visible artifact and
complete, dated, evidence-backed features exist. Test-only patient-response
artifacts are rejected. Resistance evidence without a usable date is excluded
from cutoff-valid findings, and combination candidates require a dated,
provenance-backed graph relationship explicitly tied to an evidenced
resistance mechanism. Unknown toxicity and development feasibility remain
unknown when supporting evidence is absent.

## Opportunity discovery API

`POST /api/discover` adapts the existing natural-language search parser and
asset search engine. The response includes parsed intent, supported structured
filters, matching asset identifiers, source-backed evidence references, and a
deterministic search heuristic score. That score is not an opportunity decision
or an ML prediction; calibrated candidate confidence and ML ranking remain
unavailable unless a validated model and lineage are available. Filters that
the current asset search engine cannot apply are rejected instead of silently
ignored.

Historical/as-of discovery preserves the requested cutoff but returns no
candidates while point-in-time search inputs are unavailable; current asset
data is not substituted. Saved searches can be created with `save_as` in the
request and retrieved from
`GET /api/discover/saved-searches/{saved_search_id}`. They retain the query and
structured filters in configured Redis and require trusted tenant and user
context; access is scoped to both. The current asset search source is the
AI-services fixture catalog, not a tenant-specific persistent asset index.

## Asset comparison API

`POST /api/compare` accepts 2–20 unique canonical asset IDs and an optional
`cutoff` date. It resolves IDs through the same asset catalog used by the Core
Asset APIs and reuses the existing evaluation-component aggregator for biology,
clinical, CNS, patient match, safety, resistance, competitive, licensing, and
commercial outputs. Tenant scope comes from trusted request context and is
forwarded to the cutoff-aware domain engines; callers cannot supply a tenant ID.

Each dimension retains the source output, its evidence and provenance, epistemic
state, confidence, and unknowns. Numeric scores are additionally represented on
a 0-1 scale while the original value is retained. CNS exposure/activity and
predicted potential/activity remain separate. A winner is identified only when
every compared asset has an available value for the same metric, confidence,
and supporting evidence; otherwise the result says unknown, insufficient
evidence, or not comparable. Missing safety evidence cannot create a favorable
or unfavorable winner, and categorical licensing states are not converted to
availability rankings. Contradictory evidence is marked not classified because
the reused domain outputs do not expose a common cross-domain contradiction
schema. Clinical readiness is kept separate from model-derived clinical
success probability; competitive differentiation is kept separate from
competitive risk; and all CNS measured/predicted signals are retained
separately. ML-backed metrics are compared only when model and feature lineage
match across the compared assets.

The currently configured canonical asset source is fixture-backed and contains
fewer than 20 assets; the endpoint contract accepts up to 20 when the canonical
repository contains that many. Historical safety, competitive, and commercial
outputs remain unavailable where their existing engines do not reconstruct
as-of profiles.

## Historical backtest API

`POST /api/backtest` evaluates only previously stored, tenant-scoped ML
predictions. Requests identify canonical assets, a historical prediction
cutoff, an evaluation-window end, and optional registered model, model-version,
feature-version, outcome-type, top-k, and decision-threshold selectors. Unknown
assets, duplicate/malformed IDs, unsupported model/feature combinations,
future cutoffs, and invalid evaluation windows are rejected.

Predictions are eligible only when their stored timestamp and prediction
cutoff are no later than the requested cutoff, the exact model artifact was
registered and trained by the applicable cutoff, and every required feature
has dated, version-matched, source-referenced provenance. The API never invokes
current feature-generation or serving fallbacks to recreate a historical
prediction. Model predictions are distinguished from source-backed observed
outcomes; temporal outcome records remain descriptive and are not treated as
model labels unless a stored outcome explicitly matches the model target and
has outcome evidence references. Missing predictions, outcomes, or lineage
remain `UNKNOWN` or `INSUFFICIENT_HISTORY`.

Accuracy, precision, recall, F1, AUROC, AUPRC, Brier score, and log loss use the
existing `ValidationPipeline` and are reported only with at least five
target-compatible, evidence-referenced labels. AUROC/AUPRC are undefined when
the labels do not contain both classes. Calibration uses the existing
calibration error calculation and requires at least ten such labels. Ranking
and enrichment are not computed across mixed model/feature versions, incomplete
prediction cohorts, or missing outcomes. Reported model and evidence lineage
accompanies metrics and rankings. Threshold sensitivity is explicitly
hypothetical; it does not claim causal counterfactual outcomes.

The trusted request tenant context scopes model artifacts and predictions;
tenant IDs are not accepted from request bodies. Current model, prediction,
and temporal outcome stores are in-memory. Persisted outcome evidence
references are preserved by the API but are not independently resolved
against an external evidence catalog. The existing canonical asset catalog is
fixture-backed. Consequently, historical ML predictions and target-aligned
metrics may be unavailable even when descriptive dated outcomes exist.

Prompt 60 focused tests: `tests/test_prompt_60_backtest_api.py` (19 passed).
The API/temporal/ML/intelligence regression selection (including Prompts
43–49 and 55–60) passed 138 tests. Validation commands and results:

```powershell
Set-Location 'apps/ai-services'
python -m pytest tests\test_prompt_60_backtest_api.py -q
# 19 passed
python -m pytest tests\test_prompt_43_ml.py tests\test_prompt_44_45_46_intelligence.py tests\test_prompt_47_48_49_intelligence.py tests\test_prompt_55_56_intelligence.py tests\test_prompt_57_core_apis.py tests\test_prompt_58_discover_api.py tests\test_prompt_59_compare_api.py tests\test_prompt_60_backtest_api.py tests\test_temporal_intelligence.py tests\test_opportunity_engine.py tests\test_ml_explainability_monitoring.py -q
# 138 passed
python -m compileall -q app
# passed
Set-Location '../..'
git diff --check
# passed
```

Prompt 60 status: **PROMPT 60 — COMPLETE**. Prompt 61 and later work remains
out of scope; Phase 13 has not been started.
