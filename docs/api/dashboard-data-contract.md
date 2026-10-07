# AI-RxOS: Dashboard Data Contract Specification
**Document ID:** `NZ-API-DASH-2026-v1.0`  
**Status:** `RATIFIED & ACTIVE`  
**Classification:** `Enterprise Architecture / Core Data Contract`  
**Target Systems:** `@ai-rxos/web`, `@ai-rxos/ui`, `services/api-gateway`, `services/opportunity-engine`, `services/ml-inference`

---

## 1. Executive Overview & Constitutional Invariants

This specification defines the typed backend contracts for every major dashboard component in the Neozenone AI-RxOS Drug Opportunity Discovery Engine. In strict compliance with the **Product Constitution (`NZ-CONST-2026-v1.0`)**:

1. **Every Dashboard Score Must Be Backed by a Typed API Object:** No numerical metric or percentage gauge may exist as a bare primitive number. Every score carries an explicit value, scale, confidence interval, sample size, model lineage, feature snapshot ID, and epistemic classification.
2. **Zero-Hallucination Unknown State:** Missing, unobserved, or statistically underpowered data must be rendered as an explicit typed `UNKNOWN` or `INSUFFICIENT_EVIDENCE` state with structured gap rationale and study recommendations. The UI must never invent data or interpolate values without provenance.
3. **Strict Epistemic Provenance:** Every claim, feature, and visual badge is strictly classified into one of seven epistemic states:
   - `VERIFIED` — Directly corroborated by peer-reviewed literature, clinical registry, or regulatory filing.
   - `INFERRED` — Multi-hop relational inference synthesized by knowledge graph reasoning.
   - `PREDICTED` — Deterministic output from calibrated statistical/ML models with versioned weights.
   - `HYPOTHESIS` — Mechanistic biological hypothesis generated from pre-clinical analogies.
   - `UNKNOWN` — Documented translational knowledge gap requiring targeted confirmatory trials.
   - `CONFLICTING` — Dual contradictory signals actively preserved for bias mitigation.
   - `INSUFFICIENT_EVIDENCE` — Observation exists but sample size ($n$) or statistical power fails minimum confidence thresholds.
4. **End-to-End Lineage DAG:** Every dashboard component contract defines its source database entities, normalization pipeline, intermediate feature transformations, and inference model IDs.

---

## 2. Universal Contract Primitives & Envelopes

Every endpoint delivering data to the dashboard conforms to deterministic contract primitives.

### 2.1 Universal Score Contract (`ScoredMetric<T>`)

```typescript
export interface ScoreLineage {
  calculation_formula: string;
  formula_version: string;
  model_id: string;
  model_version: string;
  feature_snapshot_id: string;
  observation_ids: string[]; // UUIDs of underlying raw observations
  computed_at: string; // ISO 8601 UTC
}

export interface ScoreConfidence {
  score: number; // 0.00 to 1.00 (epistemic confidence)
  confidence_interval: [number, number]; // e.g. [0.72, 0.88] (95% CI)
  sample_size: number | null; // e.g. n=142
  p_value: number | null; // e.g. p < 0.001
  epistemic_uncertainty: number; // Model uncertainty (0.0 to 1.0)
  aleatoric_uncertainty: number; // Data noise uncertainty (0.0 to 1.0)
  calibration_notes?: string;
}

export type EpistemicStatus =
  | "VERIFIED"
  | "INFERRED"
  | "PREDICTED"
  | "HYPOTHESIS"
  | "UNKNOWN"
  | "CONFLICTING"
  | "INSUFFICIENT_EVIDENCE";

export interface ScoredMetric<T = number> {
  metric_key: string;
  display_name: string;
  value: T;
  min_value: number;
  max_value: number;
  unit: string; // "%", "nM", "score", "months"
  qualitative_tier?: "Very Low" | "Low" | "Moderate" | "High" | "Very High";
  confidence: ScoreConfidence;
  lineage: ScoreLineage;
  epistemic_status: EpistemicStatus;
  uncertainty_rationale?: string | null;
  benchmark_comparison?: {
    benchmark_asset_id: string;
    benchmark_name: string;
    benchmark_value: T;
    delta: number;
    statistical_significance: boolean;
  } | null;
}
```

### 2.2 Universal Provenance & Citation Lineage

```typescript
export interface CitationReference {
  citation_id: string;
  source_type: "literature" | "clinical_trial" | "regulatory_label" | "patent" | "conference_abstract";
  source_ref: string; // "NCT03939026", "PMID:38830112", "US-11020394-B2"
  short_citation: string; // "Modi et al., NEJM (2022)"
  full_citation: string;
  doi?: string | null;
  url: string | null;
  publication_year: number;
  as_of_date: string;
  peer_reviewed: boolean;
  verified_by_curator: boolean;
}

export interface LineageTraceNode {
  node_id: string;
  node_type: "raw_source" | "extraction" | "normalized_observation" | "derived_feature" | "ml_model" | "decision_node";
  name: string;
  version: string;
  timestamp: string;
  hash: string;
}

export interface ComponentProvenance {
  citations: CitationReference[];
  lineage_dag: LineageTraceNode[];
  temporal_scope: {
    as_of_date: string;
    valid_from: string;
    valid_to: string | null;
    is_temporal_cutoff_compliant: boolean;
  };
}
```

### 2.3 Universal API Response, Loading, & Error Envelopes

```typescript
export interface ApiResponseMeta {
  request_id: string;
  timestamp: string;
  as_of_date: string;
  tenant_id: string;
  execution_duration_ms: number;
  cache_hit: boolean;
  schema_version: string;
}

export interface ApiResponse<T> {
  status: "success" | "partial" | "unknown";
  data: T;
  meta: ApiResponseMeta;
  provenance: ComponentProvenance;
}

export interface ApiLoadingState<T> {
  status: "loading";
  progress_percentage: number;
  current_stage: "retrieving_graph" | "extracting_features" | "running_inference" | "synthesizing_dossier";
  estimated_time_remaining_ms: number;
  partial_data: Partial<T> | null;
}

export interface ApiErrorDetail {
  code: string;
  message: string;
  field?: string;
  component: string;
  remediation_suggestion: string;
  lineage_node_failed?: string;
}

export interface ApiErrorResponse {
  status: "error";
  error: {
    code: string;
    message: string;
    details: ApiErrorDetail[];
    support_dossier_id: string;
  };
  meta: ApiResponseMeta;
}
```

---

## 3. Component-by-Component Backend Contracts

---

### 3.1 `AssetHeader` (Asset Overview & Dossier Header)

#### Component Role
Displays canonical asset metadata, status classification, developer/owner, modality, clinical stage, and primary indication setting.

#### TypeScript & Zod Schema
```typescript
import { z } from "zod";

export const AssetHeaderPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  name: z.string().min(1),
  code_name: z.string().nullable().optional(),
  target: z.string().min(1),
  modality: z.enum([
    "SMALL_MOLECULE",
    "ANTIBODY",
    "ADC",
    "PROTEIN",
    "PEPTIDE",
    "CELL_THERAPY",
    "GENE_THERAPY",
    "RNA_THERAPY",
    "RADIOPHARMACEUTICAL",
  ]),
  stage: z.enum(["Preclinical", "Phase I", "Phase II", "Phase III", "Approved", "Terminated"]),
  status_label: z.enum(["Investigational", "Approved", "Preclinical", "Terminated"]),
  owner: z.string().min(1),
  primary_indication: z.string().min(1),
  main_differentiation: z.string(),
  cns_penetrant: z.boolean(),
  canonical_smiles: z.string().nullable().optional(),
  molecular_weight: z.number().nullable().optional(),
});
export type AssetHeaderPayload = z.infer<typeof AssetHeaderPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/header`
- **Query Params:** `as_of_date` (optional temporal cutoff)
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "name": "Zanidatamab",
    "code_name": "ZW25",
    "target": "HER2 (ECD2 & ECD4 Bispecific)",
    "modality": "ANTIBODY",
    "stage": "Phase III",
    "status_label": "Investigational",
    "owner": "Jazz Pharmaceuticals / Zymeworks",
    "primary_indication": "HER2-Amplified Biliary Tract Cancer / HER2+ GEA",
    "main_differentiation": "Biparatopic dual-epitope receptor clustering with robust endocytosis",
    "cns_penetrant": false,
    "canonical_smiles": null,
    "molecular_weight": 150000.0
  },
  "meta": {
    "request_id": "req-9843-hdr",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 14,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [
      {
        "citation_id": "cit-001",
        "source_type": "clinical_trial",
        "source_ref": "NCT04466891",
        "short_citation": "HERIZON-BTC-01 Trial",
        "full_citation": "ClinicalTrials.gov ID: NCT04466891, A Study of Zanidatamab (ZW25) in Subjects With Advanced or Metastatic HER2-Amplified Biliary Tract Cancer.",
        "url": "https://clinicaltrials.gov/study/NCT04466891",
        "publication_year": 2023,
        "as_of_date": "2026-10-01",
        "peer_reviewed": true,
        "verified_by_curator": true
      }
    ],
    "lineage_dag": [
      {
        "node_id": "kg-node-asset-01",
        "node_type": "normalized_observation",
        "name": "CanonicalAssetRecord",
        "version": "v1.2",
        "timestamp": "2026-10-01T00:00:00Z",
        "hash": "sha256-a79f182b"
      }
    ],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2020-01-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

#### Source Database & KG Fields
- `canonical_entities.preferred_name` $\rightarrow$ `name`
- `canonical_entities.attributes->>'code_name'` $\rightarrow$ `code_name`
- `canonical_entities.modality` $\rightarrow$ `modality`
- `canonical_entities.attributes->>'stage'` $\rightarrow$ `stage`
- `canonical_relationships(SUBJECT=Asset, PREDICATE=TARGETS, OBJECT=Gene)` $\rightarrow$ `target`
- `canonical_relationships(SUBJECT=Company, PREDICATE=OWNS_ASSET, OBJECT=Asset)` $\rightarrow$ `owner`

#### Evidence Lineage
`Raw NCT/PubMed Record` $\rightarrow$ `Entity Normalizer (v2.1)` $\rightarrow$ `Canonical Asset Graph Node` $\rightarrow$ `AssetHeader API DTO`.

#### Confidence Specification
- Categorical attributes: Strict verification against FDA/EMA registry or NCT clinical trials record.
- Verification score: $1.0$ (deterministic fact).

#### Unknown State Contract
```json
{
  "status": "partial",
  "data": {
    "asset_id": "b2c3d4e5-unknown-asset",
    "name": "Investigational Molecule X",
    "code_name": null,
    "target": "UNKNOWN",
    "modality": "OTHER",
    "stage": "Preclinical",
    "status_label": "Investigational",
    "owner": "UNKNOWN / Undisclosed Originator",
    "primary_indication": "UNKNOWN",
    "main_differentiation": "Pharmacological mechanism not yet disclosed in public disclosures",
    "cns_penetrant": false
  }
}
```

#### Loading State Contract
Returns skeleton payload with `status: "loading"`, placeholder bounding boxes, and active spinner metadata.

#### Error State Contract
- `ERR_ASSET_NOT_FOUND` (404)
- `ERR_ASSET_ARCHIVED` (410)

---

### 3.2 `DecisionBanner` & `DecisionBadge` (Strategic Triage Decision)

#### Component Role
Renders the primary executive recommendation: `PURSUE`, `INVESTIGATE`, `PARTNER`, `LICENSE`, `MONITOR`, `AVOID`, or `INSUFFICIENT_EVIDENCE`.

#### TypeScript & Zod Schema
```typescript
export const DecisionBannerPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  action: z.enum(["PURSUE", "INVESTIGATE", "PARTNER", "LICENSE", "MONITOR", "AVOID", "INSUFFICIENT_EVIDENCE"]),
  decision_title: z.string(),
  rationale: z.string(),
  theme: z.enum(["green", "amber", "blue", "rose", "slate"]),
  confidence_metric: z.custom<ScoredMetric<number>>(),
  decision_timestamp: z.string().datetime(),
  review_status: z.enum(["automated_engine", "human_ratified", "dissenting_review"]),
  ratified_by: z.string().nullable().optional(),
});
export type DecisionBannerPayload = z.infer<typeof DecisionBannerPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/recommendation/banner`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "action": "PURSUE",
    "decision_title": "High-Priority Asset — PURSUE",
    "rationale": "Superior biparatopic target binding selectivity with verified clinical efficacy in HER2-amplified refractory indications and favorable safety tolerability over standard second-line TKIs.",
    "theme": "green",
    "confidence_metric": {
      "metric_key": "decision_confidence",
      "display_name": "Strategic Decision Confidence",
      "value": 91.5,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "qualitative_tier": "Very High",
      "confidence": {
        "score": 0.92,
        "confidence_interval": [88.0, 95.0],
        "sample_size": 284,
        "p_value": 0.0001,
        "epistemic_uncertainty": 0.05,
        "aleatoric_uncertainty": 0.03
      },
      "lineage": {
        "calculation_formula": "Weighted Bayesian Decision Utility (Efficacy * 0.35 + Safety * 0.25 + Commercial * 0.20 + Differentiation * 0.20)",
        "formula_version": "v2.4",
        "model_id": "model-bayesian-triage",
        "model_version": "2026.3",
        "feature_snapshot_id": "feat-snap-9921",
        "observation_ids": ["obs-101", "obs-102", "obs-103", "obs-104"],
        "computed_at": "2026-10-01T14:32:00Z"
      },
      "epistemic_status": "PREDICTED"
    },
    "decision_timestamp": "2026-10-01T14:32:00Z",
    "review_status": "automated_engine",
    "ratified_by": null
  },
  "meta": {
    "request_id": "req-9844-bnr",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 22,
    "cache_hit": false,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [
      {
        "citation_id": "cit-002",
        "source_type": "literature",
        "source_ref": "PMID:37385278",
        "short_citation": "Harding et al., Lancet Oncol (2023)",
        "full_citation": "Harding JJ, et al. Zanidatamab for previously treated HER2-amplified biliary tract cancer (HERIZON-BTC-01): a multicentre, single-arm, phase 2b study. Lancet Oncol. 2023;24(7):772-782.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/37385278/",
        "publication_year": 2023,
        "as_of_date": "2026-10-01",
        "peer_reviewed": true,
        "verified_by_curator": true
      }
    ],
    "lineage_dag": [
      {
        "node_id": "model-triage-v24",
        "node_type": "ml_model",
        "name": "BayesianDecisionUtilityEngine",
        "version": "v2.4",
        "timestamp": "2026-10-01T14:32:00Z",
        "hash": "sha256-ff819c92"
      }
    ],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2023-07-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

#### Source Database & KG Fields
- `decision_recommendations.action` $\rightarrow$ `action`
- `decision_recommendations.rationale` $\rightarrow$ `rationale`
- `decision_recommendations.confidence` $\rightarrow$ `confidence_metric.confidence.score`
- `decision_recommendations.model_lineage` $\rightarrow$ `confidence_metric.lineage`

#### Evidence Lineage
`EvidenceObservationRich` $\rightarrow$ `DerivedFeature` $\rightarrow$ `BayesianDecisionUtilityEngine` $\rightarrow$ `DecisionRecommendation` $\rightarrow$ `DecisionBanner`.

#### Confidence Specification
Requires minimum sample size $n \ge 30$ and epistemic confidence $\ge 0.60$ for conclusive action; otherwise forces `INSUFFICIENT_EVIDENCE`.

#### Unknown State Contract
When underlying trial evidence is inconclusive:
```json
{
  "status": "partial",
  "data": {
    "action": "INSUFFICIENT_EVIDENCE",
    "decision_title": "Indeterminate Signal — INSUFFICIENT EVIDENCE",
    "rationale": "Reported pre-clinical cohorts lack statistical power (n < 15) to confirm in vivo therapeutic window.",
    "theme": "amber",
    "confidence_metric": {
      "value": 35.0,
      "epistemic_status": "INSUFFICIENT_EVIDENCE",
      "uncertainty_rationale": "High epistemic variance across contradictory in vitro assays."
    }
  }
}
```

#### Loading & Error States
- **Loading:** Stream chunk `stage: "running_decision_utility_model"`.
- **Error:** `ERR_DECISION_MODEL_DRIFT`, `ERR_LINEAGE_UNRESOLVED`.

---

### 3.3 `RecommendationPanel` (Comprehensive Decision Dossier)

#### Component Role
Detailed strategic dossier panel displaying supporting drivers, toxicological contraindications, model lineage, and human-in-the-loop sign-off state.

#### TypeScript & Zod Schema
```typescript
export const RecommendationPanelPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  action: z.enum(["PURSUE", "INVESTIGATE", "PARTNER", "LICENSE", "MONITOR", "AVOID", "INSUFFICIENT_EVIDENCE"]),
  rationale: z.string(),
  supporting_drivers: z.array(z.string().min(1)),
  contraindications: z.array(z.string().min(1)),
  development_potential: z.custom<ScoredMetric<number>>(),
  decision_confidence: z.custom<ScoredMetric<number>>(),
  governance_audit: z.object({
    audit_hash: z.string(),
    model_version: z.string(),
    feature_set_version: z.string(),
    temporal_cutoff_date: z.string(),
    human_signoff_required: z.boolean(),
    signed_off_at: z.string().nullable().optional(),
    signed_off_by: z.string().nullable().optional(),
  }),
});
export type RecommendationPanelPayload = z.infer<typeof RecommendationPanelPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/recommendation/dossier`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "action": "PURSUE",
    "rationale": "High-conviction development opportunity driven by validated Phase 2b confirmed objective response rates (41.3%) in refractory BTC with manageable Grade 1-2 diarrhea safety profile.",
    "supporting_drivers": [
      "Biparatopic binding induces robust HER2 receptor internalization and down-modulation",
      "Phase 2b HERIZON-BTC-01 showed 41.3% confirmed ORR and 12.9 months median DOR",
      "Significant differentiation against Trastuzumab and Tukysa in refractory setting",
      "FDA Breakthrough Therapy and Fast Track designations granted"
    ],
    "contraindications": [
      "Grade 3 treatment-related diarrhea observed in 4.7% of trial population",
      "Negligible blood-brain barrier penetration; inactive in active brain metastases without combination partner"
    ],
    "development_potential": {
      "metric_key": "dps_score",
      "display_name": "Development Potential Score",
      "value": 87.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "qualitative_tier": "Very High",
      "confidence": {
        "score": 0.91,
        "confidence_interval": [83.0, 91.0],
        "sample_size": 284,
        "p_value": 0.0001,
        "epistemic_uncertainty": 0.09,
        "aleatoric_uncertainty": 0.04
      },
      "lineage": {
        "calculation_formula": "Calibrated Bayesian Transition Likelihood (P_Ind * P_Ph1 * P_Ph2 * P_Ph3)",
        "formula_version": "v1.4",
        "model_id": "model-dps-bayesian",
        "model_version": "2026.1",
        "feature_snapshot_id": "snap-8841",
        "observation_ids": ["obs-dps-01", "obs-dps-02"],
        "computed_at": "2026-10-01T14:30:00Z"
      },
      "epistemic_status": "PREDICTED"
    },
    "decision_confidence": {
      "metric_key": "decision_confidence",
      "display_name": "Decision Confidence",
      "value": 93.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "qualitative_tier": "Very High",
      "confidence": {
        "score": 0.93,
        "confidence_interval": [90.0, 96.0],
        "sample_size": 284,
        "p_value": null,
        "epistemic_uncertainty": 0.07,
        "aleatoric_uncertainty": 0.03
      },
      "lineage": {
        "calculation_formula": "Bayesian Information Criterion Composite",
        "formula_version": "v1.0",
        "model_id": "model-conf-calc",
        "model_version": "2026.1",
        "feature_snapshot_id": "snap-8841",
        "observation_ids": ["obs-c-01"],
        "computed_at": "2026-10-01T14:30:00Z"
      },
      "epistemic_status": "PREDICTED"
    },
    "governance_audit": {
      "audit_hash": "sha256-88a4e921d782",
      "model_version": "model-dps-bayesian:2026.1",
      "feature_set_version": "feat-v2.1",
      "temporal_cutoff_date": "2026-10-01",
      "human_signoff_required": true,
      "signed_off_at": null,
      "signed_off_by": null
    }
  },
  "meta": {
    "request_id": "req-9845-dos",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 31,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [
      {
        "citation_id": "cit-002",
        "source_type": "literature",
        "source_ref": "PMID:37385278",
        "short_citation": "Harding et al., Lancet Oncol (2023)",
        "full_citation": "Lancet Oncol. 2023;24(7):772-782.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/37385278/",
        "publication_year": 2023,
        "as_of_date": "2026-10-01",
        "peer_reviewed": true,
        "verified_by_curator": true
      }
    ],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2023-07-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

#### Lineage & Database Mapping
- `decision_recommendations` table joined with `recommendation_drivers` and `recommendation_contraindications`.

---

### 3.4 `ScoreCard` & `ScoreGauge` (Universal Scientific Scoring Gauges)

#### Component Role
Renders numerical metrics (e.g. DPS, Safety Score, Selectivity Index, Match Score) as structured cards or radial SVG dials.

#### TypeScript & Zod Schema
```typescript
export const ScoreCardPayloadSchema = z.object({
  metric: z.custom<ScoredMetric<number>>(),
  visual_theme: z.enum(["emerald", "amber", "rose", "blue"]),
  show_confidence_interval: z.boolean().default(true),
  show_benchmark: z.boolean().default(true),
  display_mode: z.enum(["card", "gauge", "compact"]),
});
export type ScoreCardPayload = z.infer<typeof ScoreCardPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/metrics/{metric_key}`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "metric": {
      "metric_key": "target_selectivity",
      "display_name": "HER2 vs EGFR Selectivity Index",
      "value": 92.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "score",
      "qualitative_tier": "Very High",
      "confidence": {
        "score": 0.94,
        "confidence_interval": [88.0, 96.0],
        "sample_size": 18,
        "p_value": 0.001,
        "epistemic_uncertainty": 0.06,
        "aleatoric_uncertainty": 0.02
      },
      "lineage": {
        "calculation_formula": "log10(IC50_EGFR / IC50_HER2) normalized to 0-100 linear scale",
        "formula_version": "v1.1",
        "model_id": "assay-normalizer-enzymatic",
        "model_version": "v1.0",
        "feature_snapshot_id": "snap-assay-301",
        "observation_ids": ["obs-ic50-egfr", "obs-ic50-her2"],
        "computed_at": "2026-10-01T12:00:00Z"
      },
      "epistemic_status": "VERIFIED",
      "benchmark_comparison": {
        "benchmark_asset_id": "b-tucatinib-01",
        "benchmark_name": "Tucatinib",
        "benchmark_value": 85.0,
        "delta": 7.0,
        "statistical_significance": true
      }
    },
    "visual_theme": "emerald",
    "show_confidence_interval": true,
    "show_benchmark": true,
    "display_mode": "card"
  },
  "meta": {
    "request_id": "req-9846-sc",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 12,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [
      {
        "citation_id": "cit-003",
        "source_type": "literature",
        "source_ref": "PMID:30126922",
        "short_citation": "Li et al., Mol Cancer Ther (2018)",
        "full_citation": "Mol Cancer Ther. 2018;17(11):2363-2374.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/30126922/",
        "publication_year": 2018,
        "as_of_date": "2026-10-01",
        "peer_reviewed": true,
        "verified_by_curator": true
      }
    ],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2018-11-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.5 `WhyPanel` (Factor Attribution Waterfall)

#### Component Role
Explains the recommendation by decomposing net scores into attributable feature additions and penalties ($\pm$ points).

#### TypeScript & Zod Schema
```typescript
export const FactorAttributionItemSchema = z.object({
  factor_key: z.string(),
  name: z.string(),
  impact_points: z.number(), // positive or negative points
  category: z.enum(["biology", "cns", "patient", "safety", "stage", "commercial"]),
  rationale: z.string(),
  confidence: z.number().min(0).max(1),
  source_evidence_ids: z.array(z.string().uuid()),
});

export const WhyPanelPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  baseline_score: z.number(),
  final_net_score: z.number(),
  factors: z.array(FactorAttributionItemSchema),
  attribution_model_lineage: z.string(),
});
export type WhyPanelPayload = z.infer<typeof WhyPanelPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/recommendation/attribution`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "baseline_score": 50.0,
    "final_net_score": 87.0,
    "factors": [
      {
        "factor_key": "feat-bi-01",
        "name": "Biparatopic HER2 Selectivity",
        "impact_points": 18.0,
        "category": "biology",
        "rationale": "Distinct ECD2/ECD4 dual binding drives enhanced receptor cross-linking and down-regulation over monovalent antibodies.",
        "confidence": 0.94,
        "source_evidence_ids": ["c0a80120-0001-4000-8000-000000000001"]
      },
      {
        "factor_key": "feat-clin-02",
        "name": "Phase 2b Clinical Validation",
        "impact_points": 16.0,
        "category": "stage",
        "rationale": "High confirmed response rate (41.3% ORR) in heavily pre-treated biliary tract cancer cohort.",
        "confidence": 0.92,
        "source_evidence_ids": ["c0a80120-0002-4000-8000-000000000002"]
      },
      {
        "factor_key": "feat-cns-03",
        "name": "Lack of Monotherapy CNS Activity",
        "impact_points": -7.0,
        "category": "cns",
        "rationale": "Intact IgG antibody does not cross intact blood-brain barrier; limits monotherapy utility in brain metastatic settings.",
        "confidence": 0.89,
        "source_evidence_ids": ["c0a80120-0003-4000-8000-000000000003"]
      },
      {
        "factor_key": "feat-comm-04",
        "name": "First-in-Class Biliary Exclusivity",
        "impact_points": 10.0,
        "category": "commercial",
        "rationale": "First targeted biologic to obtain Priority Review in second-line HER2+ biliary cancer, commanding strong pricing power.",
        "confidence": 0.91,
        "source_evidence_ids": ["c0a80120-0004-4000-8000-000000000004"]
      }
    ],
    "attribution_model_lineage": "SHAP Shapley-Value Attribution Engine v1.8 (KernelExplainer calibrated on 450 historic oncology assets)"
  },
  "meta": {
    "request_id": "req-9847-why",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 28,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.6 `RadarProfile` & `BiologyProfile` (6D Biology & Mechanism Profile)

#### Component Role
Renders the 6-axis pharmacological profile:
1. `target_selectivity`
2. `potency`
3. `safety_ti`
4. `clinical_readiness`
5. `biomarker_strategy`
6. `cns_potential`

#### TypeScript & Zod Schema
```typescript
export const BiologyProfilePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  metrics: z.object({
    target_selectivity: z.custom<ScoredMetric<number>>(),
    potency: z.custom<ScoredMetric<number>>(),
    safety_ti: z.custom<ScoredMetric<number>>(),
    clinical_readiness: z.custom<ScoredMetric<number>>(),
    biomarker_strategy: z.custom<ScoredMetric<number>>(),
    cns_potential: z.custom<ScoredMetric<number>>(),
  }),
  benchmark_asset: z.object({
    asset_id: z.string().uuid(),
    asset_name: z.string(),
    metrics: z.object({
      target_selectivity: z.number(),
      potency: z.number(),
      safety_ti: z.number(),
      clinical_readiness: z.number(),
      biomarker_strategy: z.number(),
      cns_potential: z.number(),
    }),
  }).nullable().optional(),
});
export type BiologyProfilePayload = z.infer<typeof BiologyProfilePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/biology/profile`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "metrics": {
      "target_selectivity": {
        "metric_key": "target_selectivity",
        "display_name": "Target Selectivity",
        "value": 94.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "score",
        "qualitative_tier": "Very High",
        "confidence": { "score": 0.95, "confidence_interval": [90.0, 98.0], "sample_size": 24, "p_value": null, "epistemic_uncertainty": 0.05, "aleatoric_uncertainty": 0.02 },
        "lineage": { "calculation_formula": "In vitro SPR binding KD ratio vs HER1/HER3/HER4", "formula_version": "v1.0", "model_id": "spr-assay-fit", "model_version": "1.0", "feature_snapshot_id": "snap-01", "observation_ids": ["obs-spr-1"], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "potency": {
        "metric_key": "potency",
        "display_name": "In Vitro Potency",
        "value": 88.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "score",
        "qualitative_tier": "High",
        "confidence": { "score": 0.92, "confidence_interval": [84.0, 92.0], "sample_size": 32, "p_value": null, "epistemic_uncertainty": 0.08, "aleatoric_uncertainty": 0.03 },
        "lineage": { "calculation_formula": "pIC50 Antiproliferative Cell Viability Index (AU565 / SKBR3)", "formula_version": "v1.2", "model_id": "potency-agg", "model_version": "1.0", "feature_snapshot_id": "snap-02", "observation_ids": ["obs-p-1"], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "safety_ti": {
        "metric_key": "safety_ti",
        "display_name": "Therapeutic Index",
        "value": 82.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "score",
        "qualitative_tier": "High",
        "confidence": { "score": 0.88, "confidence_interval": [76.0, 88.0], "sample_size": 80, "p_value": null, "epistemic_uncertainty": 0.12, "aleatoric_uncertainty": 0.05 },
        "lineage": { "calculation_formula": "NOAEL Cyno vs Effective Human Exposure Margin", "formula_version": "v2.0", "model_id": "tox-ti-fit", "model_version": "1.0", "feature_snapshot_id": "snap-03", "observation_ids": ["obs-ti-1"], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "clinical_readiness": {
        "metric_key": "clinical_readiness",
        "display_name": "Clinical Readiness",
        "value": 90.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "score",
        "qualitative_tier": "Very High",
        "confidence": { "score": 0.98, "confidence_interval": [88.0, 92.0], "sample_size": 284, "p_value": null, "epistemic_uncertainty": 0.02, "aleatoric_uncertainty": 0.01 },
        "lineage": { "calculation_formula": "Phase 2b Complete / BLA Filed Transition Index", "formula_version": "v1.0", "model_id": "stage-readiness", "model_version": "1.0", "feature_snapshot_id": "snap-04", "observation_ids": ["obs-cr-1"], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "biomarker_strategy": {
        "metric_key": "biomarker_strategy",
        "display_name": "Biomarker Strategy",
        "value": 86.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "score",
        "qualitative_tier": "High",
        "confidence": { "score": 0.90, "confidence_interval": [81.0, 91.0], "sample_size": 140, "p_value": null, "epistemic_uncertainty": 0.10, "aleatoric_uncertainty": 0.04 },
        "lineage": { "calculation_formula": "HER2 IHC 3+ / ISH+ Genomic Stratification Rigor", "formula_version": "v1.1", "model_id": "biomarker-fit", "model_version": "1.0", "feature_snapshot_id": "snap-05", "observation_ids": ["obs-bm-1"], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "cns_potential": {
        "metric_key": "cns_potential",
        "display_name": "CNS Penetration Potential",
        "value": 25.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "score",
        "qualitative_tier": "Low",
        "confidence": { "score": 0.91, "confidence_interval": [18.0, 32.0], "sample_size": 12, "p_value": null, "epistemic_uncertainty": 0.09, "aleatoric_uncertainty": 0.04 },
        "lineage": { "calculation_formula": "CSF-to-Plasma Partition Coefficient (Kp,uu,brain) and Antibody Mw Penalty", "formula_version": "v1.5", "model_id": "cns-penetration-model", "model_version": "1.2", "feature_snapshot_id": "snap-06", "observation_ids": ["obs-cns-1"], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "PREDICTED"
      }
    },
    "benchmark_asset": {
      "asset_id": "b-tucatinib-01",
      "asset_name": "Tucatinib (Tukysa)",
      "metrics": {
        "target_selectivity": 88.0,
        "potency": 82.0,
        "safety_ti": 76.0,
        "clinical_readiness": 98.0,
        "biomarker_strategy": 82.0,
        "cns_potential": 85.0
      }
    }
  },
  "meta": {
    "request_id": "req-9848-bio",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 19,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.7 `ClinicalStage` & `Timeline` (Clinical Pipeline & Milestone Tracker)

#### Component Role
Tracks the developmental lifecycle of the molecule across global regulatory and clinical milestone phases.

#### TypeScript & Zod Schema
```typescript
export const MilestoneItemSchema = z.object({
  id: z.string().uuid(),
  date: z.string(), // "2024-Q3" or "2023-11-15"
  title: z.string(),
  category: z.enum(["trial", "regulatory", "preclinical", "patent", "deal"]),
  status: z.enum(["completed", "in_progress", "projected"]),
  description: z.string().nullable().optional(),
  evidence_citation_id: z.string().nullable().optional(),
});

export const ClinicalStagePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  current_stage: z.enum(["Preclinical", "Phase I", "Phase II", "Phase III", "Approved"]),
  highest_stage_passed: z.enum(["Preclinical", "Phase I", "Phase II", "Phase III", "Approved"]),
  pipeline_stepper: z.array(
    z.object({
      stage_name: z.string(),
      status: z.enum(["passed", "active", "future"]),
      started_year: z.number().nullable().optional(),
      completion_year_estimated: z.number().nullable().optional(),
    })
  ),
  milestones: z.array(MilestoneItemSchema),
});
export type ClinicalStagePayload = z.infer<typeof ClinicalStagePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/clinical/timeline`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "current_stage": "Phase III",
    "highest_stage_passed": "Phase II",
    "pipeline_stepper": [
      { "stage_name": "Preclinical", "status": "passed", "started_year": 2016, "completion_year_estimated": 2018 },
      { "stage_name": "Phase I", "status": "passed", "started_year": 2018, "completion_year_estimated": 2021 },
      { "stage_name": "Phase II", "status": "passed", "started_year": 2020, "completion_year_estimated": 2023 },
      { "stage_name": "Phase III", "status": "active", "started_year": 2022, "completion_year_estimated": 2026 },
      { "stage_name": "Approved", "status": "future", "started_year": null, "completion_year_estimated": 2026 }
    ],
    "milestones": [
      {
        "id": "e0a80120-0001-4000-8000-000000000001",
        "date": "2023-06-02",
        "title": "HERIZON-BTC-01 Phase 2b Trial Readout",
        "category": "trial",
        "status": "completed",
        "description": "Primary endpoint met with 41.3% confirmed ORR at ASCO 2023 Plenary Session.",
        "evidence_citation_id": "cit-002"
      },
      {
        "id": "e0a80120-0002-4000-8000-000000000002",
        "date": "2024-05-29",
        "title": "FDA BLA Acceptance with Priority Review",
        "category": "regulatory",
        "status": "completed",
        "description": "BLA accepted for priority review in previously treated HER2-positive biliary tract cancer.",
        "evidence_citation_id": "cit-004"
      },
      {
        "id": "e0a80120-0003-4000-8000-000000000003",
        "date": "2026-Q1",
        "title": "Phase 3 HERIZON-GEA-01 First-Line Readout",
        "category": "trial",
        "status": "in_progress",
        "description": "Randomized Phase 3 comparing Zanidatamab + chemo +/- tislelizumab vs trastuzumab + chemo in 1L HER2+ GEA.",
        "evidence_citation_id": "cit-005"
      }
    ]
  },
  "meta": {
    "request_id": "req-9849-stg",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 16,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2016-01-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.8 `DevelopmentPotential` (Bayesian Stage Transition Probabilities & DPS)

#### Component Role
Calculates the calibrated Bayesian likelihood of advancing across regulatory development gates to final approval.

#### TypeScript & Zod Schema
```typescript
export const DevelopmentPotentialPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  development_potential_score: z.custom<ScoredMetric<number>>(),
  stage_transitions: z.object({
    preclinical_to_ind: z.custom<ScoredMetric<number>>(),
    phase_i_to_ii: z.custom<ScoredMetric<number>>(),
    phase_ii_to_iii: z.custom<ScoredMetric<number>>(),
    phase_iii_to_approval: z.custom<ScoredMetric<number>>(),
  }),
  calibration_metadata: z.object({
    benchmark_family: z.string(),
    historical_transition_rate_baseline: z.number(),
    bayesian_updating_factor: z.number(),
    model_version: z.string(),
    calibration_notes: z.string(),
  }),
});
export type DevelopmentPotentialPayload = z.infer<typeof DevelopmentPotentialPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/clinical/development-potential`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "development_potential_score": {
      "metric_key": "dps_composite",
      "display_name": "Development Potential Score",
      "value": 87.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "qualitative_tier": "Very High",
      "confidence": { "score": 0.91, "confidence_interval": [82.0, 92.0], "sample_size": 284, "p_value": null, "epistemic_uncertainty": 0.09, "aleatoric_uncertainty": 0.04 },
      "lineage": {
        "calculation_formula": "Cumulative Bayesian Likelihood calibrated against oncology benchmarks",
        "formula_version": "v1.4",
        "model_id": "model-dps-bayesian",
        "model_version": "2026.1",
        "feature_snapshot_id": "feat-snap-dps-01",
        "observation_ids": ["obs-dps-tr-01"],
        "computed_at": "2026-10-01T14:00:00Z"
      },
      "epistemic_status": "PREDICTED"
    },
    "stage_transitions": {
      "preclinical_to_ind": {
        "metric_key": "p_ind",
        "display_name": "Preclinical → IND",
        "value": 96.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "%",
        "confidence": { "score": 0.98, "confidence_interval": [95.0, 98.0], "sample_size": 1, "p_value": null, "epistemic_uncertainty": 0.02, "aleatoric_uncertainty": 0.01 },
        "lineage": { "calculation_formula": "Historical Fact (Passed)", "formula_version": "v1.0", "model_id": "fact-check", "model_version": "1.0", "feature_snapshot_id": "f-01", "observation_ids": [], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "phase_i_to_ii": {
        "metric_key": "p_ph1_ph2",
        "display_name": "Phase I → Phase II",
        "value": 91.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "%",
        "confidence": { "score": 0.98, "confidence_interval": [90.0, 93.0], "sample_size": 1, "p_value": null, "epistemic_uncertainty": 0.02, "aleatoric_uncertainty": 0.01 },
        "lineage": { "calculation_formula": "Historical Fact (Passed)", "formula_version": "v1.0", "model_id": "fact-check", "model_version": "1.0", "feature_snapshot_id": "f-02", "observation_ids": [], "computed_at": "2026-10-01T00:00:00Z" },
        "epistemic_status": "VERIFIED"
      },
      "phase_ii_to_iii": {
        "metric_key": "p_ph2_ph3",
        "display_name": "Phase II → Phase III",
        "value": 85.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "%",
        "confidence": { "score": 0.95, "confidence_interval": [80.0, 90.0], "sample_size": 87, "p_value": null, "epistemic_uncertainty": 0.05, "aleatoric_uncertainty": 0.03 },
        "lineage": { "calculation_formula": "Bayesian Updated Posterior given 41.3% ORR (Prior: 0.38, Update: 2.23)", "formula_version": "v2.0", "model_id": "bayesian-trans-engine", "model_version": "2026.1", "feature_snapshot_id": "f-03", "observation_ids": ["obs-p2-readout"], "computed_at": "2026-10-01T14:00:00Z" },
        "epistemic_status": "PREDICTED"
      },
      "phase_iii_to_approval": {
        "metric_key": "p_ph3_app",
        "display_name": "Phase III → Regulatory Approval",
        "value": 78.0,
        "min_value": 0.0,
        "max_value": 100.0,
        "unit": "%",
        "confidence": { "score": 0.88, "confidence_interval": [71.0, 84.0], "sample_size": 142, "p_value": null, "epistemic_uncertainty": 0.12, "aleatoric_uncertainty": 0.05 },
        "lineage": { "calculation_formula": "Bayesian Posterior calibrated on Priority Review Designation and interim OS trend", "formula_version": "v2.0", "model_id": "bayesian-trans-engine", "model_version": "2026.1", "feature_snapshot_id": "f-04", "observation_ids": ["obs-p3-interim"], "computed_at": "2026-10-01T14:00:00Z" },
        "epistemic_status": "PREDICTED"
      }
    },
    "calibration_metadata": {
      "benchmark_family": "Targeted HER2 Bispecific & Monoclonal Antibodies in Solid Oncology",
      "historical_transition_rate_baseline": 0.42,
      "bayesian_updating_factor": 1.85,
      "model_version": "BayesianTrans_Oncology_v2026.1",
      "calibration_notes": "Predictions calibrated on 1,420 historical solid tumor oncology trials (2010-2025) and verified pharmacology."
    }
  },
  "meta": {
    "request_id": "req-9850-dps",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 25,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.9 `PatientMatch` (Genomic Stratification & Biomarker Cohorts)

#### Component Role
Stratifies responder patient subpopulations, biomarker criteria, and active central nervous system benefit status.

#### TypeScript & Zod Schema
```typescript
export const PatientMatchPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  best_patient_population: z.array(z.string().min(1)),
  biomarkers: z.array(
    z.object({
      gene_symbol: z.string(),
      alteration_type: z.enum(["Amplification", "Overexpression", "Mutation", "Fusion", "Wildtype"]),
      assay_method: z.string(), // "IHC 3+", "FISH / ISH+", "NGS"
      prevalence_in_indication: z.string(), // "~15-20%"
      diagnostic_kit_approved: z.boolean(),
    })
  ),
  disease_setting: z.string(),
  prior_lines_of_therapy: z.string(),
  cns_metastases_benefit: z.boolean(),
  cns_benefit_evidence_summary: z.string().nullable().optional(),
  match_confidence_metric: z.custom<ScoredMetric<number>>(),
});
export type PatientMatchPayload = z.infer<typeof PatientMatchPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/patient-match`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "best_patient_population": [
      "HER2-amplified (IHC 3+ or IHC 2+/ISH+) metastatic Biliary Tract Cancer (BTC) refractory to gemcitabine-cisplatin",
      "HER2-positive (IHC 3+) metastatic gastroesophageal adenocarcinoma (GEA) in 1st-line combination",
      "HER2-mutated non-amplified solid tumors (exploratory agnostic basket cohort)"
    ],
    "biomarkers": [
      {
        "gene_symbol": "ERBB2",
        "alteration_type": "Amplification",
        "assay_method": "IHC 3+ or ISH (ratio ≥ 2.0)",
        "prevalence_in_indication": "~15% to 20% in BTC",
        "diagnostic_kit_approved": true
      },
      {
        "gene_symbol": "ERBB2",
        "alteration_type": "Mutation",
        "assay_method": "Tissue / ctDNA NGS (Exon 19/20 kinase domain)",
        "prevalence_in_indication": "~2% to 4% in non-amplified pan-tumor",
        "diagnostic_kit_approved": false
      }
    ],
    "disease_setting": "Metastatic / Locally Advanced Inoperable",
    "prior_lines_of_therapy": "Second-line or later (BTC); First-line (GEA trial ongoing)",
    "cns_metastases_benefit": false,
    "cns_benefit_evidence_summary": "Preclinical and clinical trial protocols excluded active untreated brain metastases; antibody molecular weight (150 kDa) precludes adequate blood-brain barrier penetration without BBB disruption or combination with brain-penetrant small molecule TKIs.",
    "match_confidence_metric": {
      "metric_key": "patient_match_confidence",
      "display_name": "Patient Cohort Match Confidence",
      "value": 89.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "qualitative_tier": "High",
      "confidence": { "score": 0.89, "confidence_interval": [85.0, 93.0], "sample_size": 284, "p_value": null, "epistemic_uncertainty": 0.11, "aleatoric_uncertainty": 0.04 },
      "lineage": {
        "calculation_formula": "Genomic Responder Stratification Enrichment Model",
        "formula_version": "v1.2",
        "model_id": "model-patient-strat",
        "model_version": "1.0",
        "feature_snapshot_id": "snap-strat-01",
        "observation_ids": ["obs-strat-btc"],
        "computed_at": "2026-10-01T00:00:00Z"
      },
      "epistemic_status": "VERIFIED"
    }
  },
  "meta": {
    "request_id": "req-9851-pm",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 20,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [
      {
        "citation_id": "cit-002",
        "source_type": "literature",
        "source_ref": "PMID:37385278",
        "short_citation": "Harding et al., Lancet Oncol (2023)",
        "full_citation": "Lancet Oncol. 2023;24(7):772-782.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/37385278/",
        "publication_year": 2023,
        "as_of_date": "2026-10-01",
        "peer_reviewed": true,
        "verified_by_curator": true
      }
    ],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2023-07-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.10 `SafetyProfile` (Adverse Events, TI & Organ Toxicity)

#### Component Role
Provides clinical and pre-clinical safety telemetry: common AEs, Grade 3+ toxicities, DLTs, cardiac risk, and discontinuations.

#### TypeScript & Zod Schema
```typescript
export const AdverseEventItemSchema = z.object({
  term: z.string(),
  grade_1_2_rate: z.number(), // percentage
  grade_3_plus_rate: z.number(), // percentage
  is_dose_limiting: z.boolean(),
  organ_system: z.string(),
});

export const SafetyProfilePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  common_aes_summary: z.string(),
  dose_limiting_toxicities: z.string(),
  therapeutic_index: z.string(),
  discontinuation_rate: z.string(),
  cardiac_lvef_risk: z.string(),
  gi_toxicity_grade: z.enum(["Mild", "Low-Moderate", "Moderate", "High"]),
  detailed_adverse_events: z.array(AdverseEventItemSchema),
  safety_score: z.custom<ScoredMetric<number>>(),
});
export type SafetyProfilePayload = z.infer<typeof SafetyProfilePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/safety/profile`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "common_aes_summary": "Diarrhea (52.3% any grade), Infusion-related reactions (32.8%), Fatigue (15.6%), Nausea (14.1%)",
    "dose_limiting_toxicities": "None defined in Phase 2b; MTD not reached up to 20 mg/kg biweekly",
    "therapeutic_index": "Favorable wide therapeutic window; low cardiotoxicity relative to trastuzumab combinations",
    "discontinuation_rate": "2.3% treatment discontinuation due to adverse events",
    "cardiac_lvef_risk": "Low (Grade 1 asymptomatic LVEF decrease in 1.2% of patients; no Grade 3+ heart failure)",
    "gi_toxicity_grade": "Low-Moderate",
    "detailed_adverse_events": [
      { "term": "Diarrhea", "grade_1_2_rate": 47.6, "grade_3_plus_rate": 4.7, "is_dose_limiting": false, "organ_system": "Gastrointestinal" },
      { "term": "Infusion-related reaction", "grade_1_2_rate": 31.2, "grade_3_plus_rate": 1.6, "is_dose_limiting": false, "organ_system": "Immunologic" },
      { "term": "Decreased ejection fraction", "grade_1_2_rate": 1.2, "grade_3_plus_rate": 0.0, "is_dose_limiting": false, "organ_system": "Cardiac" },
      { "term": "Interstitial lung disease", "grade_1_2_rate": 0.0, "grade_3_plus_rate": 0.0, "is_dose_limiting": true, "organ_system": "Pulmonary" }
    ],
    "safety_score": {
      "metric_key": "safety_tolerability_score",
      "display_name": "Overall Safety & Tolerability Score",
      "value": 84.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "score",
      "qualitative_tier": "High",
      "confidence": { "score": 0.93, "confidence_interval": [80.0, 88.0], "sample_size": 284, "p_value": null, "epistemic_uncertainty": 0.07, "aleatoric_uncertainty": 0.03 },
      "lineage": {
        "calculation_formula": "100 - (2.0 * Gr3_Rate + 0.5 * Gr1_2_Rate + 5.0 * Discontinuation_Rate)",
        "formula_version": "v1.3",
        "model_id": "tox-scoring-engine",
        "model_version": "2026.1",
        "feature_snapshot_id": "f-tox-01",
        "observation_ids": ["obs-tox-ae-01"],
        "computed_at": "2026-10-01T00:00:00Z"
      },
      "epistemic_status": "VERIFIED"
    }
  },
  "meta": {
    "request_id": "req-9852-saf",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 17,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [
      {
        "citation_id": "cit-002",
        "source_type": "literature",
        "source_ref": "PMID:37385278",
        "short_citation": "Harding et al., Lancet Oncol (2023)",
        "full_citation": "Lancet Oncol. 2023;24(7):772-782.",
        "url": "https://pubmed.ncbi.nlm.nih.gov/37385278/",
        "publication_year": 2023,
        "as_of_date": "2026-10-01",
        "peer_reviewed": true,
        "verified_by_curator": true
      }
    ],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2023-07-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.11 `ResistanceProfile` (Predicted Escape Pathways & Mutations)

#### Component Role
Identifies biochemical and genomic bypass mechanisms, target gatekeeper mutations, and cellular escape pathways.

#### TypeScript & Zod Schema
```typescript
export const ResistanceMechanismPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  mechanisms: z.array(
    z.object({
      mechanism_id: z.string().uuid(),
      name: z.string(),
      impact: z.enum(["High", "Moderate", "Low"]),
      is_predicted: z.boolean(),
      description: z.string(),
      bypass_pathway: z.string(),
      evidence_polarity: z.enum(["SUPPORTING", "CONTRADICTING"]),
      citation_ids: z.array(z.string()),
    })
  ),
  overall_resistance_risk_score: z.custom<ScoredMetric<number>>(),
});
export type ResistanceMechanismPayload = z.infer<typeof ResistanceMechanismPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/biology/resistance`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "mechanisms": [
      {
        "mechanism_id": "d0a80120-0001-4000-8000-000000000001",
        "name": "PI3K/AKT Pathway Hyperactivation (PIK3CA Mutations)",
        "impact": "High",
        "is_predicted": true,
        "description": "Downstream activation of PI3K/AKT axis (e.g. E545K or H1047R mutations) bypasses HER2 extracellular blockade, blunting antibody-mediated apoptosis.",
        "bypass_pathway": "PI3K/AKT/mTOR signaling cascade",
        "evidence_polarity": "SUPPORTING",
        "citation_ids": ["cit-006"]
      },
      {
        "mechanism_id": "d0a80120-0002-4000-8000-000000000002",
        "name": "HER2 Extracellular Domain Truncation (p95HER2)",
        "impact": "Moderate",
        "is_predicted": true,
        "description": "Proteolytic cleavage shedding the ECD2/ECD4 epitopes leaves constitutively active kinase domain lacking binding sites.",
        "bypass_pathway": "Direct receptor truncation",
        "evidence_polarity": "SUPPORTING",
        "citation_ids": ["cit-007"]
      },
      {
        "mechanism_id": "d0a80120-0003-4000-8000-000000000003",
        "name": "MET / AXL Receptor Tyrosine Kinase Upregulation",
        "impact": "Moderate",
        "is_predicted": true,
        "description": "Parallel RTK heterodimerization signaling compensations in prolonged monotherapy exposure.",
        "bypass_pathway": "Parallel receptor tyrosine kinase bypass",
        "evidence_polarity": "SUPPORTING",
        "citation_ids": ["cit-008"]
      }
    ],
    "overall_resistance_risk_score": {
      "metric_key": "resistance_risk_index",
      "display_name": "Acquired Resistance Vulnerability Index",
      "value": 68.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "score",
      "qualitative_tier": "Moderate",
      "confidence": { "score": 0.85, "confidence_interval": [60.0, 75.0], "sample_size": 42, "p_value": null, "epistemic_uncertainty": 0.15, "aleatoric_uncertainty": 0.08 },
      "lineage": {
        "calculation_formula": "Knowledge Graph Multi-Hop Pathway Resistance Model",
        "formula_version": "v1.2",
        "model_id": "kg-pathway-escape-model",
        "model_version": "2026.1",
        "feature_snapshot_id": "f-kg-res-01",
        "observation_ids": ["obs-res-01"],
        "computed_at": "2026-10-01T00:00:00Z"
      },
      "epistemic_status": "PREDICTED"
    }
  },
  "meta": {
    "request_id": "req-9853-res",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 23,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.12 `CombinationCard` (Rational Synergistic Regimens)

#### Component Role
Presents biochemically and clinically rational drug combination strategies to prevent escape mechanisms or potentiate cytotoxic killing.

#### TypeScript & Zod Schema
```typescript
export const CombinationCardPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  combinations: z.array(
    z.object({
      combination_id: z.string().uuid(),
      partner_name: z.string(),
      partner_modality: z.string(),
      partner_target: z.string(),
      synergy_type: z.enum([
        "Dual Target Pathway Inhibition",
        "Immunogenic Cell Death Synergy",
        "Overcoming Extracellular Truncation",
        "Synthetic Lethality",
        "Pharmacokinetic Potentiation",
      ]),
      rationale: z.string(),
      clinical_status: z.string(),
      in_vivo_synergy_score: z.number().min(0).max(100),
      evidence_ids: z.array(z.string()),
    })
  ),
});
export type CombinationCardPayload = z.infer<typeof CombinationCardPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/biology/combinations`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "combinations": [
      {
        "combination_id": "c1a80120-0001-4000-8000-000000000001",
        "partner_name": "CAPOX / mFOLFOX6 (Chemotherapy)",
        "partner_modality": "CYTOTOXIC_CHEMO",
        "partner_target": "DNA Synthesis / Thymidylate Synthase",
        "synergy_type": "Immunogenic Cell Death Synergy",
        "rationale": "Chemotherapy induces cell-surface stress antigens and enhances antibody-dependent cellular cytotoxicity (ADCC) and complement activation.",
        "clinical_status": "Phase 3 HERIZON-GEA-01 Active Trial",
        "in_vivo_synergy_score": 92.0,
        "evidence_ids": ["c0a80120-comb-01"]
      },
      {
        "combination_id": "c1a80120-0002-4000-8000-000000000002",
        "partner_name": "Tislelizumab (Anti-PD-1)",
        "partner_modality": "ANTIBODY",
        "partner_target": "PD-1",
        "synergy_type": "Dual Target Pathway Inhibition",
        "rationale": "Overcomes checkpoint exhaustion induced by prolonged local antibody-dependent inflammation; promotes sustained cytotoxic T cell tumor infiltration.",
        "clinical_status": "Phase 3 Triple Combination Arm (NCT05152147)",
        "in_vivo_synergy_score": 87.0,
        "evidence_ids": ["c0a80120-comb-02"]
      },
      {
        "combination_id": "c1a80120-0003-4000-8000-000000000003",
        "partner_name": "Tucatinib (Small Molecule TKI)",
        "partner_modality": "SMALL_MOLECULE",
        "partner_target": "HER2 Intracellular Kinase Domain",
        "synergy_type": "Overcoming Extracellular Truncation",
        "rationale": "Simultaneous intracellular and extracellular HER2 blockade; tucatinib confers potent CNS brain metastasis protection lacking in naked antibody monotherapy.",
        "clinical_status": "Investigator-Sponsored Phase 1/2 Protocol",
        "in_vivo_synergy_score": 84.0,
        "evidence_ids": ["c0a80120-comb-03"]
      }
    ]
  },
  "meta": {
    "request_id": "req-9854-cmb",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 19,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.13 `CompetitiveLandscape` (Direct Benchmarks & FTO Disclaimer)

#### Component Role
Head-to-head comparison of rights ownership, patent expiry, direct clinical assets, and mandatory freedom-to-operate disclaimer.

#### TypeScript & Zod Schema
```typescript
export const CompetitiveLandscapePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  current_owner: z.string(),
  patent_ip_window: z.string(),
  commercial_opportunity_summary: z.string(),
  competitive_assets: z.array(
    z.object({
      name: z.string(),
      owner: z.string(),
      stage: z.string(),
      modality: z.string(),
      relative_advantage_over_target: z.string(),
      relative_weakness_against_target: z.string(),
    })
  ),
  licensing_partnering_feasibility: z.string(),
  fto_legal_disclaimer: z.string(),
});
export type CompetitiveLandscapePayload = z.infer<typeof CompetitiveLandscapePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/business/competitive`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "current_owner": "Jazz Pharmaceuticals (Global Rights excl. Asia-Pacific) / Zymeworks / BeiGene (Asia-Pacific)",
    "patent_ip_window": "Core bispecific composition of matter patents extend through 2036 with potential Hatch-Waxman PTE through 2039",
    "commercial_opportunity_summary": "First targeted biologic opportunity in 2L HER2+ BTC (~12,000 global addressable patients/yr) with line extension into 1L GEA (~45,000 patients/yr).",
    "competitive_assets": [
      {
        "name": "Trastuzumab deruxtecan (Enhertu)",
        "owner": "Daiichi Sankyo / AstraZeneca",
        "stage": "Approved (Pan-Tumor HER2 IHC 3+ / Breast / Gastric / NSCLC)",
        "modality": "ADC (Topoisomerase I Inhibitor)",
        "relative_advantage_over_target": "Higher standalone response rates in low-HER2 expressors due to bystander cytotoxic payload.",
        "relative_weakness_against_target": "Significant interstitial lung disease (ILD) toxicity risk (Grade 3-5 fatalities in ~2%); requires frequent monitoring."
      },
      {
        "name": "Tucatinib (Tukysa)",
        "owner": "Seagen / Pfizer",
        "stage": "Approved (HER2+ mBC / mCRC)",
        "modality": "SMALL_MOLECULE (TKI)",
        "relative_advantage_over_target": "Potent blood-brain barrier CNS penetration with proven brain metastasis active overall survival prolongation.",
        "relative_weakness_against_target": "Requires combination with capecitabine + trastuzumab; Grade 3 elevated ALT/AST hepatotoxicity."
      }
    ],
    "licensing_partnering_feasibility": "Fully partnered worldwide (Jazz Pharmaceuticals paid $325M upfront in 2022). Potential regional ex-US / ex-EU distribution co-development partnering feasible only via Jazz or BeiGene.",
    "fto_legal_disclaimer": "AI-RxOS decision intelligence signals do not constitute formal legal freedom-to-operate (FTO) opinions, non-infringement certifications, or validity warranties under 35 U.S.C. Legal counsel must independently examine active patent claims prior to transaction closing."
  },
  "meta": {
    "request_id": "req-9855-cmp",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 22,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.14 `LicensingProfile` (Deal Feasibility & Rights Ownership)

#### Component Role
Synthesizes business development, licensing availability, territory structures, and comparable deal precedents.

#### TypeScript & Zod Schema
```typescript
export const LicensingProfilePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  rights_owner: z.string(),
  feasibility_status: z.enum(["AVAILABLE", "PARTNERED", "ENCUMBERED", "ACQUIRED", "DISPUTED"]),
  feasibility_assessment: z.string(),
  patent_window: z.string(),
  territory_availability: z.string(),
  deal_precedents: z.array(
    z.object({
      deal_title: z.string(),
      licensor: z.string(),
      licensee: z.string(),
      year: number,
      upfront_usd_millions: z.number().nullable().optional(),
      total_deal_size_usd_millions: z.number().nullable().optional(),
      therapeutic_scope: z.string(),
    })
  ),
});
export type LicensingProfilePayload = z.infer<typeof LicensingProfilePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/business/licensing`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "rights_owner": "Jazz Pharmaceuticals (Global ex-Asia) / BeiGene (Asia-Pacific) / Zymeworks (Originator)",
    "feasibility_status": "PARTNERED",
    "feasibility_assessment": "Direct in-licensing unavailable due to exclusive global licenses executed in 2018 (BeiGene) and 2022 (Jazz). Out-licensing or co-commercialization sublicensing restricted to specific specialty uncommitted indications.",
    "patent_window": "2036 (Core composition of matter); 2038-2041 (Formulation and combination methods)",
    "territory_availability": "Global territories encumbered; regional sublicensing or downstream royalty monetizations negotiable via secondary corporate transactions.",
    "deal_precedents": [
      {
        "deal_title": "Jazz Pharmaceuticals Exclusive License Agreement for Zanidatamab",
        "licensor": "Zymeworks",
        "licensee": "Jazz Pharmaceuticals",
        "year": 2022,
        "upfront_usd_millions": 325.0,
        "total_deal_size_usd_millions": 1760.0,
        "therapeutic_scope": "Exclusive rights in US, Europe, Japan, and all global territories excluding BeiGene Asia territories."
      },
      {
        "deal_title": "BeiGene Strategic Collaboration Agreement for ZW25 / ZW49",
        "licensor": "Zymeworks",
        "licensee": "BeiGene",
        "year": 2018,
        "upfront_usd_millions": 40.0,
        "total_deal_size_usd_millions": 430.0,
        "therapeutic_scope": "Exclusive development and commercialization rights in Asia (excluding Japan), Australia, and New Zealand."
      }
    ]
  },
  "meta": {
    "request_id": "req-9856-lic",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 18,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2022-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.15 `CommercialOpportunity` (Addressable Populations & Revenue Forecast)

#### Component Role
Quantifies target epidemiological market sizing, addressable patient populations, and estimated peak annual sales.

#### TypeScript & Zod Schema
```typescript
export const CommercialOpportunityPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  peak_sales_estimate: z.custom<ScoredMetric<number>>(),
  addressable_annual_patients: z.number().int().positive(),
  target_indication_setting: z.string(),
  differentiation_edge: z.string(),
  opportunity_summary: z.string(),
  pricing_benchmark_per_patient_year_usd: z.number(),
  market_exclusivity_years_remaining: z.number(),
});
export type CommercialOpportunityPayload = z.infer<typeof CommercialOpportunityPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/business/commercial`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "peak_sales_estimate": {
      "metric_key": "global_peak_sales_usd_b",
      "display_name": "Estimated Global Peak Sales",
      "value": 2.2,
      "min_value": 0.0,
      "max_value": 10.0,
      "unit": "$B USD",
      "qualitative_tier": "High",
      "confidence": { "score": 0.84, "confidence_interval": [1.5, 3.1], "sample_size": 3, "p_value": null, "epistemic_uncertainty": 0.16, "aleatoric_uncertainty": 0.09 },
      "lineage": {
        "calculation_formula": "Peak Patients * Penetration Rate (28%) * Net Annual Price ($185k) * Probability of Success (0.78)",
        "formula_version": "v2.1",
        "model_id": "commercial-epidemiology-model",
        "model_version": "2026.1",
        "feature_snapshot_id": "f-comm-01",
        "observation_ids": ["obs-comm-epi-01"],
        "computed_at": "2026-10-01T00:00:00Z"
      },
      "epistemic_status": "PREDICTED"
    },
    "addressable_annual_patients": 22000,
    "target_indication_setting": "Second-line Biliary Tract Cancer (~10k) and First-line HER2+ Gastroesophageal (~12k addressable)",
    "differentiation_edge": "First approved targeted biological standard in refractory BTC with clean cardiotoxicity and low diarrhea Grade 3 discontinuation profile.",
    "opportunity_summary": "Zanidatamab represents an anchored commercial opportunity with immediate orphan niche dominance in BTC transitioning into multi-billion blockbuster potential upon successful HERIZON-GEA-01 Phase 3 readout.",
    "pricing_benchmark_per_patient_year_usd": 185000,
    "market_exclusivity_years_remaining": 13
  },
  "meta": {
    "request_id": "req-9857-com",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 21,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.16 `EvidenceCard` & `EvidenceDrawer` (Granular Provenance Records)

#### Component Role
Displays granular literature, clinical trial, or patent excerpts backing scientific assertions with verified URLs and verification states.

#### TypeScript & Zod Schema
```typescript
export const EvidenceItemPayloadSchema = z.object({
  id: z.string().uuid(),
  source_type: z.enum([
    "literature",
    "clinical_trial",
    "fda_label",
    "regulatory_authority",
    "patent",
    "conference_abstract",
  ]),
  source_ref: z.string(), // "NCT03939026"
  title: z.string(),
  citation: z.string(),
  publication_year: z.number().int(),
  url: z.string().nullable().optional(),
  excerpt: z.string(),
  polarity: z.enum(["SUPPORTING", "CONTRADICTING"]),
  epistemic_state: z.enum([
    "VERIFIED",
    "INFERRED",
    "PREDICTED",
    "HYPOTHESIS",
    "UNKNOWN",
    "CONFLICTING",
    "INSUFFICIENT_EVIDENCE",
  ]),
  is_verified: z.boolean(),
  as_of_date: z.string(),
});

export const EvidenceDrawerPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  total_count: z.number().int(),
  supporting_evidence: z.array(EvidenceItemPayloadSchema),
  contradicting_evidence: z.array(EvidenceItemPayloadSchema),
  knowledge_gaps: z.array(
    z.object({
      id: z.string().uuid(),
      category: z.string(),
      question: z.string(),
      current_gap: z.string(),
      suggested_study: z.string(),
    })
  ),
});
export type EvidenceDrawerPayload = z.infer<typeof EvidenceDrawerPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/evidence/drawer`
- **Query Params:** `polarity` (`ALL` | `SUPPORTING` | `CONTRADICTING`), `source_type`, `limit`, `offset`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "total_count": 2,
    "supporting_evidence": [
      {
        "id": "c0a80120-0001-4000-8000-000000000001",
        "source_type": "clinical_trial",
        "source_ref": "NCT04466891",
        "title": "HERIZON-BTC-01: Phase 2b Study in Advanced Biliary Tract Cancer",
        "citation": "Lancet Oncol 2023; 24(7): 772-782",
        "publication_year": 2023,
        "url": "https://pubmed.ncbi.nlm.nih.gov/37385278/",
        "excerpt": "A confirmed objective response rate of 41.3% (95% CI 30.4-52.8) was observed in cohort 1 (HER2 IHC 2+/3+). Median duration of response was 12.9 months.",
        "polarity": "SUPPORTING",
        "epistemic_state": "VERIFIED",
        "is_verified": true,
        "as_of_date": "2026-10-01"
      }
    ],
    "contradicting_evidence": [
      {
        "id": "c0a80120-0002-4000-8000-000000000002",
        "source_type": "clinical_trial",
        "source_ref": "ASCO-2023-ABS",
        "title": "Cohort 2 Negative Response Readout in HER2 IHC 0/1+ Biliary Tract Cancer",
        "citation": "J Clin Oncol 41, 2023 (suppl 16; abstr 4008)",
        "publication_year": 2023,
        "url": "https://ascopubs.org/doi/10.1200/JCO.2023.41.16_suppl.4008",
        "excerpt": "In Cohort 2 (IHC 0 or 1+ with ISH+ non-amplified expression, n=8), 0 confirmed responses were observed (0% ORR). Demonstrates strict dependency on high-level HER2 receptor density.",
        "polarity": "CONTRADICTING",
        "epistemic_state": "VERIFIED",
        "is_verified": true,
        "as_of_date": "2026-10-01"
      }
    ],
    "knowledge_gaps": [
      {
        "id": "u0a80120-0001-4000-8000-000000000001",
        "category": "Translational Unknown",
        "question": "Does Zanidatamab retain clinical activity following disease progression on Trastuzumab Deruxtecan (Enhertu)?",
        "current_gap": "Clinical sequencing data post-ADC progression is unobserved; trial protocols strictly mandated no prior HER2-targeted ADC exposure.",
        "suggested_study": "Prospective or retrospective real-world registry evaluating Zanidatamab response in patients previously treated with T-DXd."
      }
    ]
  },
  "meta": {
    "request_id": "req-9858-evd",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 27,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2023-01-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.17 `ContradictoryEvidence` (Adverse Signals & Negative Observations)

#### Component Role
Specifically isolates conflicting evidence, negative efficacy findings, toxicological failures, or refuted hypotheses to protect decision-makers from confirmation bias.

#### TypeScript & Zod Schema
```typescript
export const ContradictoryEvidencePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  contradicting_items: z.array(EvidenceItemPayloadSchema),
  bias_mitigation_statement: z.string(),
});
export type ContradictoryEvidencePayload = z.infer<typeof ContradictoryEvidencePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/evidence/contradictory`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "contradicting_items": [
      {
        "id": "c0a80120-0002-4000-8000-000000000002",
        "source_type": "clinical_trial",
        "source_ref": "ASCO-2023-ABS",
        "title": "Cohort 2 Negative Response Readout in HER2 Low Biliary Tract Cancer",
        "citation": "J Clin Oncol 41, 2023 (suppl 16; abstr 4008)",
        "publication_year": 2023,
        "url": "https://ascopubs.org/doi/10.1200/JCO.2023.41.16_suppl.4008",
        "excerpt": "0 confirmed objective responses in HER2-low (IHC 0/1+) patients, confirming lack of monotherapy bystander efficacy in tumors with low target expression.",
        "polarity": "CONTRADICTING",
        "epistemic_state": "VERIFIED",
        "is_verified": true,
        "as_of_date": "2026-10-01"
      }
    ],
    "bias_mitigation_statement": "The platform preserves negative clinical trial cohorts to guarantee recommendations do not overstate addressable market size into non-responding biomarker sub-segments."
  },
  "meta": {
    "request_id": "req-9859-cnt",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 14,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2023-01-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.18 `UnknownEvidence` (Scientific Gaps & Translational Unknowns)

#### Component Role
Exposes known unknowns, missing experimental data, unmeasured parameters, and suggests confirmatory assays.

#### TypeScript & Zod Schema
```typescript
export const UnknownFactorPayloadSchema = z.object({
  id: z.string().uuid(),
  category: z.enum(["Clinical Efficacy", "Toxicity", "Biomarker", "IP / Licensing", "Commercial"]),
  question: z.string(),
  current_gap: z.string(),
  suggested_study: z.string(),
  estimated_derisking_cost_usd: z.number().nullable().optional(),
  estimated_duration_months: z.number().nullable().optional(),
});

export const UnknownEvidencePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  unknowns: z.array(UnknownFactorPayloadSchema),
  total_critical_unknowns: z.number().int(),
});
export type UnknownEvidencePayload = z.infer<typeof UnknownEvidencePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/assets/{asset_id}/evidence/unknowns`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "unknowns": [
      {
        "id": "u0a80120-0001-4000-8000-000000000001",
        "category": "Clinical Efficacy",
        "question": "What is the true clinical efficacy in brain metastases when combined with tucatinib?",
        "current_gap": "Phase 2 trials excluded central nervous system involvement; intracranial response rates in humans have not been prospectively documented.",
        "suggested_study": "Dedicated CNS intracranial response cohort (RANO-BM criteria) in ongoing Phase 1/2 combination trial.",
        "estimated_derisking_cost_usd": 1500000,
        "estimated_duration_months": 18
      },
      {
        "id": "u0a80120-0002-4000-8000-000000000002",
        "category": "Biomarker",
        "question": "Can ctDNA genomic clearance at cycle 2 predict progression-free survival?",
        "current_gap": "Translational biomarker samples collected in HERIZON-BTC-01 have not published serial circulating tumor DNA correlation data.",
        "suggested_study": "Secondary retrospective NGS analysis on banked phase 2b plasma aliquots.",
        "estimated_derisking_cost_usd": 250000,
        "estimated_duration_months": 6
      }
    ],
    "total_critical_unknowns": 2
  },
  "meta": {
    "request_id": "req-9860-unk",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 15,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.19 `KeyAttributesTable` & `ComparisonMatrix` (Tabular Benchmark)

#### Component Role
N-dimensional tabular head-to-head comparison across 2 to $N$ assets (selectivity, IC50, mutant coverage, CNS, stages, owner, actions).

#### TypeScript & Zod Schema
```typescript
export const AttributeRowSchema = z.object({
  attribute_key: z.string(),
  attribute_label: z.string(),
  category: z.string(),
  values_by_asset_id: z.record(z.string().uuid(), z.string()),
});

export const ComparisonMatrixPayloadSchema = z.object({
  target: z.string(),
  indication: z.string(),
  assets: z.array(AssetHeaderPayloadSchema),
  attributes: z.array(AttributeRowSchema),
  head_to_head_advantages: z.record(z.string().uuid(), z.array(z.string())),
});
export type ComparisonMatrixPayload = z.infer<typeof ComparisonMatrixPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/decision/compare`
- **Query Params:** `asset_ids` (comma-separated UUIDs)
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "target": "HER2",
    "indication": "Biliary Tract & Gastroesophageal Cancer",
    "assets": [
      {
        "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
        "name": "Zanidatamab",
        "code_name": "ZW25",
        "target": "HER2 (ECD2/ECD4)",
        "modality": "ANTIBODY",
        "stage": "Phase III",
        "status_label": "Investigational",
        "owner": "Jazz Pharmaceuticals",
        "primary_indication": "BTC / GEA",
        "main_differentiation": "Biparatopic dual-epitope binding",
        "cns_penetrant": false
      },
      {
        "asset_id": "b-tucatinib-01-0000-0000-000000000001",
        "name": "Tucatinib",
        "code_name": "ONT-380",
        "target": "HER2 Kinase",
        "modality": "SMALL_MOLECULE",
        "stage": "Approved",
        "status_label": "Approved",
        "owner": "Pfizer / Seagen",
        "primary_indication": "HER2+ mBC / mCRC",
        "main_differentiation": "Highly selective kinase inhibition with active CNS penetration",
        "cns_penetrant": true
      }
    ],
    "attributes": [
      {
        "attribute_key": "selectivity",
        "attribute_label": "Selectivity",
        "category": "Pharmacology",
        "values_by_asset_id": {
          "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d": ">1,000-fold vs EGFR/HER3/HER4 (negligible EGFR inhibition)",
          "b-tucatinib-01-0000-0000-000000000001": "~1,000-fold selective for HER2 over EGFR"
        }
      },
      {
        "attribute_key": "cns_penetration",
        "attribute_label": "CNS penetration (preclinical / clinical)",
        "category": "Pharmacokinetics",
        "values_by_asset_id": {
          "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d": "Negligible (intact antibody excludes passive BBB crossing)",
          "b-tucatinib-01-0000-0000-000000000001": "Active (High brain exposure; proven HER2CLIMB active brain met benefit)"
        }
      },
      {
        "attribute_key": "action",
        "attribute_label": "Strategic Action",
        "category": "Recommendation",
        "values_by_asset_id": {
          "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d": "PURSUE",
          "b-tucatinib-01-0000-0000-000000000001": "MONITOR"
        }
      }
    ],
    "head_to_head_advantages": {
      "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d": [
        "Significantly higher standalone response rate in Biliary Tract Cancer (41.3% vs <15% for historical TKIs)",
        "Dramatically reduced systemic rash and hepatotoxicity compared to kinase inhibitors"
      ],
      "b-tucatinib-01-0000-0000-000000000001": [
        "Unrivaled CNS protection and brain metastasis intracranial control",
        "Oral small-molecule administration without clinic infusion requirements"
      ]
    }
  },
  "meta": {
    "request_id": "req-9861-cmp",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 35,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.20 `BacktestTimeline` (Temporal Zero-Leakage Simulation)

#### Component Role
Simulates what recommendation the AI-RxOS engine would have generated at a historical temporal cutoff date (e.g. 2018 or 2021), suppressing all future evidence to audit model calibration and prevent look-ahead bias.

#### TypeScript & Zod Schema
```typescript
export const BacktestTimelinePayloadSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  cutoff_date: z.string(), // "2020-01-01"
  simulation_run_id: z.string().uuid(),
  evidence_items_eligible: z.number().int(),
  evidence_items_suppressed_future: z.number().int(),
  predicted_action_at_cutoff: z.enum([
    "PURSUE",
    "INVESTIGATE",
    "PARTNER",
    "LICENSE",
    "MONITOR",
    "AVOID",
    "INSUFFICIENT_EVIDENCE",
  ]),
  predicted_development_potential: z.custom<ScoredMetric<number>>(),
  historical_recommendation_rationale: z.string(),
  ground_truth_eventual_outcome: z.string(),
  prediction_accuracy: z.enum(["True Positive", "True Negative", "Calibrated Success", "Consistent Divergence"]),
  anti_leakage_audit_passed: z.boolean(),
  leakage_audit_log: z.array(
    z.object({
      check_name: z.string(),
      passed: z.boolean(),
      detail: z.string(),
    })
  ),
});
export type BacktestTimelinePayload = z.infer<typeof BacktestTimelinePayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/backtest/simulate`
- **Query Params:** `asset_id`, `cutoff_date` (e.g. `2021-01-01`)
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
    "asset_name": "Zanidatamab",
    "cutoff_date": "2021-01-01",
    "simulation_run_id": "sim-run-7718",
    "evidence_items_eligible": 14,
    "evidence_items_suppressed_future": 89,
    "predicted_action_at_cutoff": "PURSUE",
    "predicted_development_potential": {
      "metric_key": "dps_backtest_2021",
      "display_name": "Predicted DPS at 2021 Cutoff",
      "value": 81.0,
      "min_value": 0.0,
      "max_value": 100.0,
      "unit": "%",
      "qualitative_tier": "Very High",
      "confidence": { "score": 0.86, "confidence_interval": [74.0, 87.0], "sample_size": 44, "p_value": null, "epistemic_uncertainty": 0.14, "aleatoric_uncertainty": 0.07 },
      "lineage": {
        "calculation_formula": "Temporal Cutoff Bayesian Simulation Model",
        "formula_version": "v1.1",
        "model_id": "model-backtest-sim",
        "model_version": "2021-freeze",
        "feature_snapshot_id": "snap-freeze-2021",
        "observation_ids": ["obs-2020-01"],
        "computed_at": "2026-10-01T00:00:00Z"
      },
      "epistemic_status": "PREDICTED"
    },
    "historical_recommendation_rationale": "As of Jan 1, 2021, pre-clinical biparatopic potency and early Phase 1 dose escalation demonstrated confirmed PRs in refractory HER2+ biliary cancer with 0 DLTs at planned Phase 2 dose.",
    "ground_truth_eventual_outcome": "Demonstrated 41.3% ORR in Phase 2b (2023), obtained FDA Priority Review (2024), and executed $1.76B global licensing agreement with Jazz Pharmaceuticals (2022).",
    "prediction_accuracy": "True Positive",
    "anti_leakage_audit_passed": true,
    "leakage_audit_log": [
      { "check_name": "Publication Date Horizon", "passed": true, "detail": "All 14 eligible items verified published <= 2021-01-01" },
      { "check_name": "Trial Registry Status Freeze", "passed": true, "detail": "NCT04466891 status frozen at Recruiting; future result fields masked" },
      { "check_name": "Embedding / Knowledge Graph Snapshot Freeze", "passed": true, "detail": "Graph traversal isolated to edges with valid_from <= 2021-01-01" }
    ]
  },
  "meta": {
    "request_id": "req-9862-bkt",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2021-01-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 48,
    "cache_hit": false,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2021-01-01",
      "valid_from": "2016-01-01",
      "valid_to": "2021-01-01",
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

### 3.21 `FilterPanel` & `OpportunityCard` (Faceted Portfolio Screening)

#### Component Role
Enables multi-parameter faceted filtering across portfolio assets by target class, recommendation action, stage, and CNS requirement, rendering summarized triage cards.

#### TypeScript & Zod Schema
```typescript
export const OpportunityCardPayloadSchema = z.object({
  asset_id: z.string().uuid(),
  name: z.string(),
  code_name: z.string().nullable().optional(),
  target: z.string(),
  modality: z.string(),
  stage: z.string(),
  owner: z.string(),
  primary_indication: z.string(),
  action: z.enum(["PURSUE", "INVESTIGATE", "PARTNER", "LICENSE", "MONITOR", "AVOID", "INSUFFICIENT_EVIDENCE"]),
  dps_score: z.custom<ScoredMetric<number>>(),
  main_differentiation: z.string(),
  match_confidence: number,
});

export const PortfolioScreeningPayloadSchema = z.object({
  total_matching: z.number().int(),
  applied_filters: z.object({
    target: z.string(),
    action: z.string(),
    cns_required: z.boolean(),
    stage_min: z.string().nullable().optional(),
  }),
  items: z.array(OpportunityCardPayloadSchema),
});
export type PortfolioScreeningPayload = z.infer<typeof PortfolioScreeningPayloadSchema>;
```

#### API Endpoint & Response
- **Endpoint:** `GET /api/v1/opportunities/screen`
- **Query Params:** `target` (e.g. `HER2`), `action` (e.g. `PURSUE`), `cns_required` (`true` | `false`), `limit`, `offset`
- **Response Structure:**
```json
{
  "status": "success",
  "data": {
    "total_matching": 1,
    "applied_filters": {
      "target": "HER2",
      "action": "PURSUE",
      "cns_required": false
    },
    "items": [
      {
        "asset_id": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
        "name": "Zanidatamab",
        "code_name": "ZW25",
        "target": "HER2",
        "modality": "ANTIBODY",
        "stage": "Phase III",
        "owner": "Jazz Pharmaceuticals",
        "primary_indication": "Biliary Tract Cancer",
        "action": "PURSUE",
        "dps_score": {
          "metric_key": "dps",
          "display_name": "DPS",
          "value": 87.0,
          "min_value": 0.0,
          "max_value": 100.0,
          "unit": "%",
          "qualitative_tier": "Very High",
          "confidence": { "score": 0.91, "confidence_interval": [82.0, 92.0], "sample_size": 284, "p_value": null, "epistemic_uncertainty": 0.09, "aleatoric_uncertainty": 0.04 },
          "lineage": {
            "calculation_formula": "Calibrated Bayesian Likelihood",
            "formula_version": "v1.4",
            "model_id": "model-dps",
            "model_version": "2026.1",
            "feature_snapshot_id": "snap-dps-01",
            "observation_ids": [],
            "computed_at": "2026-10-01T00:00:00Z"
          },
          "epistemic_status": "PREDICTED"
        },
        "main_differentiation": "Biparatopic dual-epitope binding with active receptor internalization",
        "match_confidence": 91.0
      }
    ]
  },
  "meta": {
    "request_id": "req-9863-scr",
    "timestamp": "2026-10-07T08:15:00Z",
    "as_of_date": "2026-10-01",
    "tenant_id": "tenant-default",
    "execution_duration_ms": 16,
    "cache_hit": true,
    "schema_version": "v1.0"
  },
  "provenance": {
    "citations": [],
    "lineage_dag": [],
    "temporal_scope": {
      "as_of_date": "2026-10-01",
      "valid_from": "2026-10-01",
      "valid_to": null,
      "is_temporal_cutoff_compliant": true
    }
  }
}
```

---

## 4. End-to-End Evidence Lineage Graph Specification

To enforce complete auditability, the system exposes a unified Directed Acyclic Graph (DAG) for every decision:

```
[Raw External Records]
  ├── PubMed (PMID:37385278)
  ├── ClinicalTrials.gov (NCT04466891)
  └── FDA Regulatory Gazette (BLA-761234)
            │
            ▼
[Entity Extraction & Canonicalization Pipeline]
  ├── ExtractionMethod: "llm_structured_extraction" (v2.1)
  ├── Extracted Text Snippet + Source Location Coordinates
  └── ValidationStatus: "validated" (Curator Verified)
            │
            ▼
[Normalized Observations (Knowledge Graph)]
  ├── obs-1: "ORR = 41.3%" (unit: "%", polarity: "SUPPORTING")
  ├── obs-2: "mDOR = 12.9 months" (polarity: "SUPPORTING")
  └── obs-3: "Gr3 Diarrhea = 4.7%" (polarity: "CONTRADICTING")
            │
            ▼
[Derived Feature Store (Feature Snapshot ID: snap-8841)]
  ├── feat-efficacy-index: 88.5 (Confidence: 0.94)
  ├── feat-safety-penalty: 14.2 (Confidence: 0.92)
  └── feat-differentiation-score: 94.0 (Confidence: 0.96)
            │
            ▼
[Calibrated Bayesian & ML Engines (Model Registry: 2026.1)]
  ├── BayesianTransitionModel (v2.0)
  ├── ToxScoringEngine (v1.3)
  └── MultiAttributeDecisionUtilityEngine (v2.4)
            │
            ▼
[Dashboard Typed API Response]
  ├── ScoredMetric: DPS = 87.0%
  ├── Action: PURSUE (Confidence: 91.5%)
  └── UI Components: AssetHeader, DecisionBanner, WhyPanel, RadarProfile
```

---

## 5. System Error Codes & Domain Fault Matrix

When an invariant is violated, the API returns a structured HTTP 4xx/5xx payload conforming to `ApiErrorResponse`:

| Error Code | HTTP Status | Root Cause | Remediation Action |
| :--- | :---: | :--- | :--- |
| `ERR_LINEAGE_BROKEN` | `500` | A derived feature or score references an observation ID that does not resolve to an external citation. | Engine halts response; flags pipeline run for ingestion rebuild. |
| `ERR_LEAKAGE_DETECTED` | `422` | In retrospective simulation mode, an observation with `publication_date > cutoff_date` entered the feature store. | Suppresses illegal nodes; reruns simulation in strict freeze mode. |
| `ERR_TEMPORAL_VIOLATION` | `400` | Requested `as_of_date` is earlier than the earliest ingested baseline epoch. | Client must supply a date within indexed temporal horizons. |
| `ERR_INSUFFICIENT_DATA_POWER` | `200 (Partial)` | Sample size $n < 15$ or epistemic confidence $< 0.50$ prevents conclusive decision tiering. | Automatically coerces strategic decision to `INSUFFICIENT_EVIDENCE`. |
| `ERR_EVIDENCE_CONFLICT_UNRESOLVED` | `200 (Partial)` | Two verified sources report divergent clinical findings without resolving meta-analysis. | Emits `CONFLICTING` visual badge with dual citation pointers. |
| `ERR_TENANT_ISOLATION_VIOLATION` | `403` | User attempts to access a proprietary tenant observation from an unauthorized organization scope. | Request rejected; security audit event logged in audit stream. |
| `ERR_MODEL_VERSION_MISMATCH` | `500` | The model version registered in feature lineage does not exist in the active ML inference model registry. | Inference orchestrator routes request to legacy container replica. |

---

## 6. Implementation Checklist & Conformance Test Suite

Every endpoint implementing this contract must pass the following automated test assertions:

1. **Primitive Score Verification:**
   - Every numerical property in `data` maps to a `ScoredMetric` object containing `lineage`, `confidence`, and `epistemic_status`.
   - Bare `number` scores return a contract lint failure.
2. **Citation Reachability:**
   - Every citation object includes either a valid `doi`, `pmid`, `nct_id`, or a reachable public URL.
3. **Temporal Cutoff Enforcement:**
   - When `as_of_date` query parameter is provided, zero records with `publication_date > as_of_date` appear in the `provenance.citations` array.
4. **Epistemic Badge Integrity:**
   - When `epistemic_status` is `UNKNOWN`, `value` is either `null`, `0`, or marked with an explicit `uncertainty_rationale`.
5. **FTO Legal Notice Mandatory Check:**
   - Any endpoint serving `CompetitiveLandscape` or `LicensingProfile` must contain the exact ratified FTO legal disclaimer text string.
