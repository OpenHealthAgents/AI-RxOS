import { z } from "zod";

export const BiologyObservationTypeSchema = z.enum([
  "IC50_BIOCHEMICAL",
  "IC50_CELLULAR",
  "SELECTIVITY_RATIO",
  "CRISPR_DEPENDENCY",
  "TARGET_VALIDITY",
  "MECHANISTIC_RATIONALE",
  "ON_TARGET_ENGAGEMENT",
  "OFF_TARGET_RISK",
  "BIOMARKER_STRATEGY",
  "GENETIC_EVIDENCE",
  "FUNCTIONAL_EVIDENCE",
  "ANIMAL_EFFICACY",
  "PATIENT_DERIVED_MODELS",
  "CLINICAL_RESPONSE",
]);
export type BiologyObservationType = z.infer<typeof BiologyObservationTypeSchema>;

export const EvaluationDimensionSchema = z.enum([
  "target_validity",
  "mechanistic_rationale",
  "potency",
  "selectivity",
  "on_target_evidence",
  "off_target_risk",
  "biomarker_strategy",
  "genetic_evidence",
  "functional_evidence",
  "translational_evidence",
  "model_diversity",
  "human_evidence",
]);
export type EvaluationDimension = z.infer<typeof EvaluationDimensionSchema>;

export const EvaluationDimensionStateSchema = z.enum([
  "VERIFIED_FACT",
  "STRONG_SUPPORT",
  "MODERATE_SUPPORT",
  "INSUFFICIENT_EVIDENCE",
  "CONTRADICTORY",
]);
export type EvaluationDimensionState = z.infer<typeof EvaluationDimensionStateSchema>;

export const RawBiologicalObservationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string(),
  parameter_name: z.string(),
  observation_type: BiologyObservationTypeSchema,
  raw_text_value: z.string(),
  normalized_value: z.number(),
  unit: z.string().nullable().optional(),
  assay_type: z.string().nullable().optional(),
  target_or_gene: z.string().nullable().optional(),
  model_system: z.string().nullable().optional(),
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  pmid: z.string().nullable().optional(),
  nct_id: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1).default(1.0),
  observation_date: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type RawBiologicalObservation = z.infer<typeof RawBiologicalObservationSchema>;

export const DimensionEvaluationSchema = z.object({
  dimension: EvaluationDimensionSchema,
  state: EvaluationDimensionStateSchema,
  raw_observation_ids: z.array(z.string().uuid()).default([]),
  raw_values_summary: z.record(z.string(), z.unknown()).default({}),
  score_contribution: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  findings: z.string(),
  evidence_citations: z.array(z.string()).default([]),
});
export type DimensionEvaluation = z.infer<typeof DimensionEvaluationSchema>;

export const ScoreFormulaLineageSchema = z.object({
  score_name: z.string(),
  formula: z.string(),
  inputs: z.record(z.string(), z.unknown()),
  raw_observation_ids: z.array(z.string().uuid()).default([]),
  calculated_value: z.number(),
  confidence_penalty_applied: z.number().default(0),
  evidence_gaps: z.array(z.string()).default([]),
});
export type ScoreFormulaLineage = z.infer<typeof ScoreFormulaLineageSchema>;

export const BiologyIntelligenceProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  biology_validation_score: z.number().min(0).max(100),
  potency_score: z.number().min(0).max(100),
  selectivity_score: z.number().min(0).max(100),
  biomarker_score: z.number().min(0).max(100),
  mechanistic_confidence: z.number().min(0).max(1),
  translational_readiness: z.number().min(0).max(100),
  dimensions: z.record(z.string(), DimensionEvaluationSchema).default({}),
  raw_observations: z.array(RawBiologicalObservationSchema).default([]),
  lineages: z.record(z.string(), ScoreFormulaLineageSchema).default({}),
  overall_confidence: z.number().min(0).max(1),
  unknowns: z.array(z.string()).default([]),
  evaluated_at: z.string().datetime().optional(),
});
export type BiologyIntelligenceProfile = z.infer<typeof BiologyIntelligenceProfileSchema>;

export const EvaluateAssetBiologyRequestSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string().nullable().optional(),
  custom_observations: z.array(RawBiologicalObservationSchema).nullable().optional(),
});
export type EvaluateAssetBiologyRequest = z.infer<typeof EvaluateAssetBiologyRequestSchema>;

export const EvaluateAssetBiologyResponseSchema = z.object({
  profile: BiologyIntelligenceProfileSchema,
});
export type EvaluateAssetBiologyResponse = z.infer<typeof EvaluateAssetBiologyResponseSchema>;
