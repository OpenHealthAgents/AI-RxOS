# Phase 9 — ML Models (Prompts 37–43)

## Status

**COMPLETE WITH DOCUMENTED LIMITATION**

This phase covers Prompt 37–43, the ML model prompts for translational biology,
clinical success, patient response, safety, CNS, resistance, and opportunity
ranking. The implementation is complete within the repository-controlled ML
runtime and deterministic test harness, but it remains intentionally limited to
local synthetic and data-integrity validation until representative historical
outcome data and deployment-grade operational controls are available.

The work follows the same pattern as earlier phase docs: implement the required
behavior, preserve the repository architecture, and document exactly what is
verified versus what remains unverified before production certification.

## Implemented flow

```text
Prompt 37 / 38 dataset builders
  -> versioned feature records + explicit observed outcomes only
  -> tenant-scoped provenance and cutoff filtering
  -> unknown outcomes preserved as None, never coerced to 0/1
  -> local ML dataset materialization for historical snapshot use

Prompt 39 patient response
  -> deterministic synthetic patient-response fixture
  -> binary response training + registry + serving + explanation + drift checks

Prompt 40 safety ML
  -> multi-target safety dataset with Grade >=3 AE, DLT, discontinuation,
     organ toxicity, and therapeutic index risk
  -> deterministic synthetic training, serving, and explanation checks

Prompt 41/42 CNS and resistance
  -> separate measured evidence from predicted potential
  -> refuse undated clinical outcomes and insufficient historical data
  -> explicit unavailable model state instead of fabricated efficacy or mechanism claims

Prompt 43 opportunity ranking
  -> typed upstream signal contract
  -> unavailable ranking outputs when model history is insufficient
  -> no fake averaging of component scores or fabricated rank values
```

## Requirement matrix

| Requirement                       | Implementation                                                                                                                                                                                                                               | Validation / result                                                                                          |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Prompt 37 — translational biology | Feature definitions and point-in-time snapshot logic are present and preserve missing values. Dataset builder accepts only explicit observed binary outcomes that are tenant-scoped, evidence-backed, and dated after the prediction cutoff. | Focused tests confirm missing outcomes stay missing and wrong-tenant/future/non-outcome records are excluded |
| Prompt 38 — clinical success      | Clinical dataset retains separate Phase II, Phase III, regulatory, and failure-probability targets. Stage is not treated as a label. Missing labels are not converted to zero or one.                                                        | Focused tests confirm unknown-label preservation and per-target metadata handling                            |
| Prompt 39 — patient response      | Deterministic synthetic fixture, training, registry registration, serving prediction, explanation, and monitoring are implemented.                                                                                                           | Prompt 39 test suite passed locally with 34 combined targeted ML tests                                       |
| Prompt 40 — safety                | Multi-output safety training and serving are implemented with explicit uncertainty handling for endpoints and missing values.                                                                                                                | Safety model path passed the deterministic test suite; synthetic-only labels remain test-only                |
| Prompt 41 — CNS prediction        | The system distinguishes measured CNS evidence from predicted CNS potential and refuses undated outcome records. Insufficient evidence produces an unavailable state.                                                                        | CNS tests passed confirming unavailable model status and evidence separation                                 |
| Prompt 42 — resistance prediction | Resistance dataset requires explicit dated observed mechanism outcomes and preserves unknown mechanisms when historical support is absent.                                                                                                   | Resistance tests passed confirming unavailable state for insufficient dated outcome history                  |
| Prompt 43 — opportunity ranking   | Ranking contract uses upstream signal metadata and returns explicit unavailable outputs when training history is insufficient. It does not silently average component scores.                                                                | Opportunity-ranking tests passed confirming unavailable output semantics                                     |
| Temporal and tenant safety        | Historical feature selectors and label selectors enforce cutoff ordering and tenant scoping.                                                                                                                                                 | Local deterministic tests cover future labels, wrong-tenant selection, and missingness handling              |
| Output validation                 | Unknown labels remain unknown instead of being converted to negative outcomes or fake clinical efficacy.                                                                                                                                     | Verified in Prompt 37/38 regression tests                                                                    |
| Model readiness semantics         | The dataset metadata reports `training_available`, `model_status`, and unavailable reasons when historical observations are insufficient.                                                                                                    | Verified in P41/P42 and P37/P38 dataset metadata tests                                                       |

## Identity and provenance

Prompt 37–43 use the repository's established ML data model rather than a
separate ad hoc framework:

- Feature records remain versioned, tenant-scoped, and provenance-backed.
- Label records preserve explicit provenance and evidence references.
- Dataset records keep `as_of_date`, prediction cutoff, tenant, and feature/label
  provenance metadata in the same schema used by the wider ML subsystem.
- Model outputs, explanations, and monitoring payloads are still tied to the
  exact model version, feature version, tenant, and recorded snapshot.

The critical correction implemented here is that model labels are not inferred
from stage, proxy signals, or current asset state unless they are explicitly
observed outcomes with enough provenance and timing information. This prevents
false training labels, leakage, and stage-based confidence inflation.

## Time and tenant semantics

The prompt 37–43 builders respect the repository's temporal safety rules:

- feature values are accepted only when their observation and prediction cutoff
  are at or before the dataset prediction cutoff;
- labels are accepted only from explicit observed outputs whose observation date
  is later than the prediction cutoff and no later than the dataset cutoff;
- future values and wrong-tenant records are excluded from dataset selection;
- unavailable or weak evidence is recorded as unknown rather than represented as
  low risk or low probability.

This is a critical condition for production readiness because the model data does
not rely on observed outcomes from the future or on cross-tenant leakage.

## API and configuration

The ML subsystem continues to use the repository's existing ML layer and model
serving architecture:

- `DatasetBuilder` and `LabelGenerator` are the canonical producers of prompt
  37–43 data objects;
- `FeatureStore` remains the source of versioned feature retrieval and tenant
  scoping;
- `TrainingPipeline` and `ModelServingEngine` execute the deterministic training
  and inference paths already used elsewhere in the ML subsystem;
- `ModelRegistry`, `PredictionStore`, and monitoring remain the persistence and
  audit boundary for evaluation and serving metadata.

No separate security or tenant framework was introduced; the repository's
existing ML architecture and scope logic were reused.

## Validation

The following command was run from `apps/ai-services`:

```powershell
& 'C:\Users\Lenovo\Downloads\AI-RxOS\.venv-1\Scripts\python.exe' -m pytest tests\test_prompt_37_38_ml.py tests\test_prompt_39_ml.py tests\test_prompt_40_ml.py tests\test_prompt_41_42_ml.py tests\test_prompt_43_ml.py -q
```

Result:

- **34 passed** in **10.86s**

Additional repository hygiene check:

```powershell
git diff --check
```

Result:

- **Passed**

## Limitations and production-readiness caveat

This implementation is complete within the repository's deterministic ML test
and local feature/data logic, but it remains limited in the following ways:

- Prompt 39 and Prompt 40 tests use deterministic synthetic fixtures, not live
  patient or safety datasets.
- Prompt 41 and Prompt 42 intentionally refuse model training when historical
  evidence is insufficient; they do not claim production readiness without a
  sufficient real-world data set.
- Prompt 43 returns explicit unavailable outputs when historical labels are
  insufficient; it does not fabricate a ranking model.
- Prompt 37 and Prompt 38 now avoid pseudo-label leakage and stage-based label
  contamination, but they still depend on the existence of real observed
  translational and clinical outcome data before a production model can be
  certified.
- No external live source validation, regulatory review, commercial deployment,
  or real-world clinical trial evidence was performed in this repository-local
  run.

## Phase closure state

| Phase                               | Closure state                       |
| ----------------------------------- | ----------------------------------- |
| Phase 2                             | Closed                              |
| Phase 3                             | Closed                              |
| Phase 4                             | Closed                              |
| Phase 5                             | Closed with documented limitation   |
| Phase 6                             | Closed with documented limitation   |
| Phase 7                             | Complete with documented limitation |
| Phase 8                             | Complete with documented limitation |
| Phase 9 — ML models (Prompts 37–43) | Complete with documented limitation |

## Final statement

The ML model prompts in this phase are implemented and verified to the extent
allowed by the repository-controlled data and deterministic tests. They are not
claimed as production-ready clinical or translational models until real,
representative historical outcome data, external validation, and deployment-grade
monitoring are completed in a governed production environment.
