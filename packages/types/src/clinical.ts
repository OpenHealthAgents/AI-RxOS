import { z } from "zod";

export const ClinicalStageSchema = z.enum([
  "PRECLINICAL",
  "PHASE_I",
  "PHASE_IB",
  "PHASE_II",
  "PHASE_II_III",
  "PHASE_III",
  "APPROVED",
  "TERMINATED",
  "WITHDRAWN",
  "CRL",
]);
export type ClinicalStage = z.infer<typeof ClinicalStageSchema>;

export const TrialDesignTypeSchema = z.enum([
  "RANDOMIZED_CONTROLLED_TRIAL",
  "SINGLE_ARM_BASKET",
  "SINGLE_ARM_EXPANSION",
  "OPEN_LABEL_DOSE_ESCALATION",
  "DOUBLE_BLIND_COMPARATOR",
  "PLATFORM_UMBRELLA",
]);
export type TrialDesignType = z.infer<typeof TrialDesignTypeSchema>;

export const EndpointReviewTypeSchema = z.enum([
  "BLINDED_INDEPENDENT_CENTRAL_REVIEW",
  "INVESTIGATOR_ASSESSED",
  "LOCAL_PATHOLOGY",
]);
export type EndpointReviewType = z.infer<typeof EndpointReviewTypeSchema>;

export const EpistemicCategorySchema = z.enum([
  "OBSERVED_CLINICAL_OUTCOME",
  "MODEL_PREDICTION",
  "EXPERT_INTERPRETATION",
  "UNKNOWN",
]);
export type EpistemicCategory = z.infer<typeof EpistemicCategorySchema>;

export const ObservedClinicalOutcomeSchema = z.object({
  id: z.string().uuid(),
  trial_id: z.string(),
  trial_title: z.string(),
  phase: ClinicalStageSchema,
  sample_size: z.number().int().nonnegative(),
  population: z.string(),
  biomarker_status: z.string(),
  orr_pct: z.number().nullable().optional(),
  cr_pct: z.number().nullable().optional(),
  dor_months: z.number().nullable().optional(),
  pfs_months: z.number().nullable().optional(),
  pfs_hazard_ratio: z.number().nullable().optional(),
  os_months: z.number().nullable().optional(),
  os_hazard_ratio: z.number().nullable().optional(),
  cbr_pct: z.number().nullable().optional(),
  grade_3_plus_ae_pct: z.number().nullable().optional(),
  treatment_discontinuation_pct: z.number().nullable().optional(),
  dose_reduction_pct: z.number().nullable().optional(),
  endpoint_review: EndpointReviewTypeSchema.default("INVESTIGATOR_ASSESSED"),
  source_citation: z.string(),
  pmid: z.string().nullable().optional(),
  reported_date: z.string().nullable().optional(),
});
export type ObservedClinicalOutcome = z.infer<typeof ObservedClinicalOutcomeSchema>;

export const ClinicalModelPredictionSchema = z.object({
  id: z.string().uuid(),
  parameter: z.string(),
  predicted_value: z.number(),
  confidence_interval_low: z.number().nullable().optional(),
  confidence_interval_high: z.number().nullable().optional(),
  model_name: z.string().default("Bayesian Oncology Transition Model v2.4"),
  calibration_methodology: z.string().default("Historical contemporary oncology benchmark calibrated"),
  prediction_date: z.string().nullable().optional(),
});
export type ClinicalModelPrediction = z.infer<typeof ClinicalModelPredictionSchema>;

export const ClinicalExpertInterpretationSchema = z.object({
  id: z.string().uuid(),
  topic: z.string(),
  consensus_view: z.string(),
  regulatory_precedent: z.string().nullable().optional(),
  clinician_summary: z.string(),
  expert_source: z.string().default("Oncology Clinical Advisory Consensus"),
});
export type ClinicalExpertInterpretation = z.infer<typeof ClinicalExpertInterpretationSchema>;

export const TrialDesignEvaluationSchema = z.object({
  trial_id: z.string(),
  design_type: TrialDesignTypeSchema,
  enrollment_count: z.number().int().nonnegative(),
  sample_size_adequate: z.boolean(),
  comparator_arm: z.string().nullable().optional(),
  blinding_method: z.string().default("Open-Label"),
  project_optimus_compliant: z.boolean().default(true),
  randomized_dose_optimization: z.boolean().default(false),
  biomarker_prospective: z.boolean().default(true),
  adjudication: EndpointReviewTypeSchema.default("BLINDED_INDEPENDENT_CENTRAL_REVIEW"),
  execution_flags: z.array(z.string()).default([]),
});
export type TrialDesignEvaluation = z.infer<typeof TrialDesignEvaluationSchema>;

export const ClinicalScoreLineageSchema = z.object({
  score_name: z.string(),
  formula: z.string(),
  inputs: z.record(z.string(), z.unknown()),
  observed_outcome_ids: z.array(z.string().uuid()).default([]),
  calculated_value: z.number(),
  evidence_gaps: z.array(z.string()).default([]),
});
export type ClinicalScoreLineage = z.infer<typeof ClinicalScoreLineageSchema>;

export const ClinicalDevelopmentProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  stage: ClinicalStageSchema,
  clinical_success_probability: z.number().min(0).max(1),
  clinical_readiness_score: z.number().min(0).max(100),
  development_risk_score: z.number().min(0).max(100),
  evidence_confidence: z.number().min(0).max(1),
  trials_evaluated: z.array(TrialDesignEvaluationSchema).default([]),
  observed_clinical_outcomes: z.array(ObservedClinicalOutcomeSchema).default([]),
  model_predictions: z.array(ClinicalModelPredictionSchema).default([]),
  expert_interpretations: z.array(ClinicalExpertInterpretationSchema).default([]),
  unknowns: z.array(z.string()).default([]),
  lineages: z.record(z.string(), ClinicalScoreLineageSchema).default({}),
  evaluated_at: z.string().datetime().optional(),
});
export type ClinicalDevelopmentProfile = z.infer<typeof ClinicalDevelopmentProfileSchema>;

export const EvaluateAssetClinicalRequestSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string().nullable().optional(),
  custom_outcomes: z.array(ObservedClinicalOutcomeSchema).nullable().optional(),
});
export type EvaluateAssetClinicalRequest = z.infer<typeof EvaluateAssetClinicalRequestSchema>;

export const EvaluateAssetClinicalResponseSchema = z.object({
  profile: ClinicalDevelopmentProfileSchema,
});
export type EvaluateAssetClinicalResponse = z.infer<typeof EvaluateAssetClinicalResponseSchema>;
