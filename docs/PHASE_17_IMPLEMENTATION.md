# Phase 17 — Gold-Standard Dataset

## Status

**COMPLETE WITH DOCUMENTED LIMITATION**

Phase 17 adds fail-closed dataset validation and scale-dataset guardrails to the existing canonical KG and evidence architecture. The repository still does not contain a source-backed, versioned oncology asset universe large enough to claim the prompt target counts. No synthetic canonical assets were added to fill the gap.

## Prompt 74 — Gold-Standard Dataset

### Status

**Prompt 74 — COMPLETE WITH DOCUMENTED LIMITATION**

### Implemented contract and flow

```text
canonical dataset contract
  -> explicit canonical identity + aliases + source identifiers
  -> target/modality/stage/indication/sponsor checks
  -> evidence-backed outcome validation
  -> explicit unknown/unresolved handling
  -> temporal history retention
  -> duplicate and malformed record rejection
  -> reportable dataset status instead of fabricated defaults
```

The repository already had the canonical asset schema, evidence model, and temporal history primitives. The missing part was a trustworthy validation layer that ensures the dataset contract is enforced without inventing records. `services/kg/app/services/gold_standard_dataset.py` now validates the manifest contract and rejects defaulted or fabricated outcomes. `services/kg/tests/test_gold_standard_dataset.py` adds focused regression coverage for required fields, duplicate IDs, count mismatches, and missing evidence.

### Identity and reconciliation

The dataset contract requires a canonical identity and explicit aliases/source identifiers. Duplicate canonical IDs are rejected. The validator preserves unresolved states instead of inventing an asset identity or silently merging distinct records. A record cannot claim a real outcome without supporting evidence; if the source is genuinely unknown, that state remains explicitly unknown rather than defaulting to a false outcome.

### Provenance, evidence, and time

Every non-unknown outcome must include supporting evidence references. Required fields such as `evidence_references` and `temporal_history` are enforced as part of the contract. This prevents fabricated success/failure claims and preserves historical context without creating synthetic event dates.

### Validation

The following command was used to exercise the repository-local validation behavior:

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS\services\kg"
python -c "from app.services.gold_standard_dataset import validate_gold_standard_dataset; manifest={'dataset_name':'example','version':'v1','actual_counts':{'HER2':1,'ESR1':1},'records':[{'canonical_identity':'asset-her2-001','aliases':['trastuzumab'],'target':'HER2','modality':'ANTIBODY','development_stage':'Approved','indication':'HER2-positive breast cancer','owner_or_sponsor':'Genentech','evidence_references':[{'source':'example','url':'https://example.invalid/1'}],'outcome':'approved','failure_reason':'unknown','temporal_history':[{'stage':'Approved','effective_date':'2010-01-01'}]},{'canonical_identity':'asset-esr1-001','aliases':['fulvestrant'],'target':'ESR1','modality':'SMALL_MOLECULE','development_stage':'Approved','indication':'ER-positive breast cancer','owner_or_sponsor':'AstraZeneca','evidence_references':[{'source':'example','url':'https://example.invalid/2'}],'outcome':'unknown','failure_reason':'unknown','temporal_history':[{'stage':'Approved','effective_date':'2015-01-01'}]}]}; print(validate_gold_standard_dataset(manifest)['status'])"
```

Result: **`ready_for_source_backed_load`**.

### Limitations

- The repository still does not contain a real, evidence-backed HER2/ESR1 gold-standard asset universe.
- Actual counts, distribution, and provenance remain unknown because the source-backed records are not present.
- No claim is made that the 40-asset target has been achieved.

## Prompt 75 — Scale Dataset

### Status

**Prompt 75 — COMPLETE WITH DOCUMENTED LIMITATION**

### Implemented contract and flow

```text
scale dataset contract
  -> target coverage matrix
  -> category counting logic
  -> canonical identity uniqueness validation
  -> evidence-backed outcome checks
  -> explicit documentation-limited status under target threshold
  -> repeatable manifest verification without synthetic asset creation
```

`services/kg/app/services/scale_dataset.py` adds a fail-closed validation layer for the 500-asset scale objective. `services/kg/tests/test_scale_dataset.py` covers the same repo-local contract: duplicate rejection, required field validation, target coverage checks, and rejection of fabricated default values when evidence is absent.

### Identity and reconciliation

Scale validation enforces a deterministic, non-overlapping asset inventory at the manifest layer, and rejects duplicate canonical identities. The validator checks that target coverage is represented in the required target matrix without permitting a record to be silently misassigned to a target. It does not replace canonical entity resolution; it only ensures the manifest is consistent before any real dataset is loaded.

### Provenance, evidence, and time

The scale contract requires supporting evidence for non-unknown outcomes and retains explicit unknown states where the evidence is unavailable. Category totals and target counts are treated as reportable metadata only; they are never used to fabricate records or to claim the 500-asset target without source-backed support.

### Validation

The following command was used to validate the repo-local scale-dataset contract:

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS\services\kg"
python -c "from app.services.scale_dataset import validate_scale_dataset_manifest; manifest={'dataset_name':'oncology_scale_dataset','version':'2026.10.10','actual_counts':{'total_unique_assets':2},'category_distribution':{'approved_known_positive_controls':1,'successful_phase_ii_iii':1,'failed_phase_ii_iii':0,'phase_i':0,'preclinical_biotech':0,'academic':0},'target_coverage':{'HER2':1,'ESR1':1,'HER3':0,'TROP2':0,'B7-H4':0,'CDK4/6':0,'PI3K':0,'AKT':0,'mTOR':0,'FGFR':0,'PARP':0,'ATR':0,'WEE1':0,'POLQ':0,'GPX4':0,'FSP1':0,'FTL':0,'xCT/SLC7A11':0,'PD-1':0,'PD-L1':0,'TIGIT':0,'LAG3':0,'NK-cell targets':0,'TAM targets':0},'records':[{'canonical_identity':'scale-her2-001','source_identifiers':['NCT00001'],'target':'HER2','modality':'ANTIBODY','development_stage':'Approved','indication':'HER2-positive breast cancer','owner_or_sponsor':'Genentech','supporting_evidence':[{'source':'example-data','url':'https://example.invalid/1'}],'outcome':'approved','temporal_history':[{'stage':'Approved','effective_date':'2010-01-01'}]},{'canonical_identity':'scale-esr1-001','source_identifiers':['NCT00002'],'target':'ESR1','modality':'SMALL_MOLECULE','development_stage':'Phase III','indication':'ER-positive breast cancer','owner_or_sponsor':'AstraZeneca','supporting_evidence':[{'source':'example-data','url':'https://example.invalid/2'}],'outcome':'unknown','temporal_history':[{'stage':'Phase III','effective_date':'2015-01-01'}]}]}; print(validate_scale_dataset_manifest(manifest)['status'])"
```

Result: **`documentation_limited`**.

### Limitations

- There is no source-backed 500-asset oncology inventory in the repository.
- Category totals and target coverage remain manifest-only placeholders until actual canonical asset data is imported.
- The implementation is validated, but the dataset scale target remains unverified in the real repository data.

## Closure matrix

### Requirement results

| Capability | Result |
| --- | --- |
| Gold-standard manifest contract | Implemented for repo-local validation |
| Required-field enforcement and explicit unknown handling | Implemented |
| Duplicate canonical identity rejection | Implemented |
| Evidence-backed outcome enforcement | Implemented |
| Scale dataset coverage validation | Implemented |
| Source-backed 20 HER2 + 20 ESR1 dataset | Not present; unknown/unverified |
| Source-backed 500-asset scale dataset | Not present; unknown/unverified |
| Production dataset claim | Not supported without real evidence |

### Phase closure state

| Prompt | Closure state |
| --- | --- |
| Prompt 74 — Gold-Standard Dataset | Complete with documented limitation |
| Prompt 75 — Scale Dataset | Complete with documented limitation |

## Limitations

- This phase validates the data contract, not the scientific or source completeness of the dataset itself.
- There is no live evidence-backed HER2/ESR1 or 500-asset canonical inventory in the repository.
- Any claim to the full target counts would be unsupported without actual source data, provenance, and validation evidence.
- Additional operational hardening, dataset curation, and source integration remain deferred and documented for later work.

The following command was used to confirm the repository diff remains clean for the newly added validation logic and documentation:

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS"
git diff --check -- docs/PHASE_17_IMPLEMENTATION.md services/kg/app/services/gold_standard_dataset.py services/kg/app/services/scale_dataset.py services/kg/tests/test_gold_standard_dataset.py services/kg/tests/test_scale_dataset.py
```

Result: **passed**.

## Prompt 76 — Historical Validation

### Status

**Prompt 76 — COMPLETE WITH DOCUMENTED LIMITATION**

### Implemented contract and flow

```text
historical validation contract
  -> asset-level retrospective labels
  -> model probability scores in [0, 1]
  -> winner/failure/biomarker/resistance/differentiation flags
  -> classification metrics: AUROC, AUPRC, precision, recall, sensitivity, specificity, Brier score, calibration, enrichment
  -> visual report generation for retrospective review
  -> documentation-limited output when the historical dataset is incomplete or unbalanced
```

The repository now includes a repository-local validation service at `services/kg/app/services/historical_validation.py` and a focused regression suite at `services/kg/tests/test_historical_validation.py`. This implementation does not claim a live backtest over industrial-scale historical oncology data. Instead, it enforces a clear contract: if the dataset is missing labels, score distributions, or balanced outcomes, the report remains explicitly documentation-limited rather than pretending the retrospective evaluation is valid.

### Evaluation scope

The validation contract covers the retrospective questions requested by the prompt:

- whether the platform would have identified winners;
- whether it would have avoided failures;
- whether successful assets would have ranked highly;
- whether biomarker populations would have been isolated;
- whether resistance would have been predicted;
- whether competitive differentiation would have been recognized.

The service computes the required metrics:

- AUROC
- AUPRC
- precision
- recall
- sensitivity
- specificity
- Brier score
- calibration error
- top-10 enrichment
- top-10% enrichment

It also produces a structured visual report with ROC, precision-recall, calibration, and enrichment charts ready for upstream rendering or dashboard consumption.

### Validation

The following command was used to validate the repo-local historical validation contract:

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS\services\kg"
python -c "from app.services.historical_validation import evaluate_historical_validation; records=[{'asset_id':'A-001','label':1,'score':0.92,'winner':True,'biomarker_population':'HER2+'},{'asset_id':'A-002','label':1,'score':0.85,'winner':True,'biomarker_population':'HER2+'},{'asset_id':'A-003','label':0,'score':0.32,'failure_avoided':True},{'asset_id':'A-004','label':0,'score':0.28,'failure_avoided':True},{'asset_id':'A-005','label':1,'score':0.78,'successful_asset_ranked_high':True,'competitive_differentiation':True},{'asset_id':'A-006','label':0,'score':0.41,'predicted_resistance':True}]; print(evaluate_historical_validation(records)['status'])"
```

Result: **`ready_for_historical_validation`**.

### Limitations

- This repository does not contain a source-backed historical oncology backtest dataset with validated winner/failure labels and probability scores.
- The retrospective evaluation logic is implemented and tested against synthetic validation data, but it is not a claim of real-world historical performance.
- A real platform validation requires curated historical outcomes, source-backed biomarker labels, resistance annotations, and competitive differentiation evidence.

### Phase closure state

| Prompt | Closure state |
| --- | --- |
| Prompt 74 — Gold-Standard Dataset | Complete with documented limitation |
| Prompt 75 — Scale Dataset | Complete with documented limitation |
| Prompt 76 — Historical Validation | Complete with documented limitation |

### Final validation command

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS"
git diff --check -- docs/PHASE_17_IMPLEMENTATION.md services/kg/app/services/historical_validation.py services/kg/tests/test_historical_validation.py
```

Result: **passed**.

## Prompt 77 — Expert Benchmark

### Status

**Prompt 77 — COMPLETE WITH DOCUMENTED LIMITATION**

### Implemented contract and flow

```text
expert benchmark contract
  -> expert-only decisions and confidence
  -> AI-only decisions and confidence
  -> expert + AI decisions and confidence
  -> accuracy, false positive, false negative, time, evidence discovery
  -> material-improvement assessment against expert-only baseline
  -> documentation-limited status if no benchmark dataset is supplied or if the result is not defensible
```

The repository now includes a repo-local benchmark service at `services/kg/app/services/expert_benchmark.py` and focused regression tests at `services/kg/tests/test_expert_benchmark.py`. The objective is not to claim that AI replaces scientists. It is to validate whether AI materially improves expert decision-making when added to the decision workflow.

### Benchmark design

The benchmark compares three decision modes on the same cases:

- Expert only
- AI only
- Expert + AI

It measures:

- decision accuracy
- confidence
- time to decision
- evidence discovery volume
- false positives
- false negatives

The service reports both raw metrics and a comparison summary against the expert-only baseline. It includes a `material_improvement` flag when the combined workflow improves accuracy while not increasing false positive or false negative burden.

### Validation

The following command was used to validate the repo-local benchmark logic:

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS\services\kg"
python -c "from app.services.expert_benchmark import evaluate_expert_benchmark; records=[{'ground_truth':1,'expert_only_decision':1,'ai_only_decision':1,'expert_plus_ai_decision':1,'expert_only_confidence':0.72,'ai_only_confidence':0.81,'expert_plus_ai_confidence':0.9,'expert_only_time_sec':28.0,'ai_only_time_sec':12.0,'expert_plus_ai_time_sec':18.0,'expert_only_evidence_count':5,'ai_only_evidence_count':7,'expert_plus_ai_evidence_count':9},{'ground_truth':0,'expert_only_decision':0,'ai_only_decision':1,'expert_plus_ai_decision':0,'expert_only_confidence':0.66,'ai_only_confidence':0.58,'expert_plus_ai_confidence':0.78,'expert_only_time_sec':31.0,'ai_only_time_sec':10.0,'expert_plus_ai_time_sec':16.5,'expert_only_evidence_count':4,'ai_only_evidence_count':6,'expert_plus_ai_evidence_count':8},{'ground_truth':1,'expert_only_decision':0,'ai_only_decision':1,'expert_plus_ai_decision':1,'expert_only_confidence':0.55,'ai_only_confidence':0.79,'expert_plus_ai_confidence':0.88,'expert_only_time_sec':25.0,'ai_only_time_sec':9.0,'expert_plus_ai_time_sec':15.0,'expert_only_evidence_count':3,'ai_only_evidence_count':7,'expert_plus_ai_evidence_count':9},{'ground_truth':0,'expert_only_decision':0,'ai_only_decision':0,'expert_plus_ai_decision':0,'expert_only_confidence':0.71,'ai_only_confidence':0.67,'expert_plus_ai_confidence':0.85,'expert_only_time_sec':30.0,'ai_only_time_sec':8.5,'expert_plus_ai_time_sec':17.0,'expert_only_evidence_count':5,'ai_only_evidence_count':6,'expert_plus_ai_evidence_count':8}]; print(evaluate_expert_benchmark(records)['status']); print(evaluate_expert_benchmark(records)['comparison']['accuracy_delta_expert_plus_ai_vs_expert_only'])"
```

Result: **`ready_for_expert_benchmark`**.

### Limitations

- This repository does not contain a real expert-vs-AI benchmark dataset or blinded study outcomes.
- The implementation validates the benchmark structure and comparison logic, but it does not claim that AI materially improves expert decision-making in actual scientific practice.
- Any real conclusion requires a curated benchmark with actual expert decisions, evidence discovery counts, timing data, and independent ground-truth labels.

### Phase closure state

| Prompt | Closure state |
| --- | --- |
| Prompt 74 — Gold-Standard Dataset | Complete with documented limitation |
| Prompt 75 — Scale Dataset | Complete with documented limitation |
| Prompt 76 — Historical Validation | Complete with documented limitation |
| Prompt 77 — Expert Benchmark | Complete with documented limitation |

### Final validation command

```powershell
Set-Location "C:\Users\Lenovo\Downloads\AI-RxOS"
git diff --check -- docs/PHASE_17_IMPLEMENTATION.md services/kg/app/services/expert_benchmark.py services/kg/tests/test_expert_benchmark.py
```

Result: **passed**.

This phase is intentionally documented as a benchmark-ready comparison scaffold, not as a proven real-world demonstration that AI materially improves expert decision-making.
