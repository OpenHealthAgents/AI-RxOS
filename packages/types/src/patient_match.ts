import { z } from "zod";

export const PopulationTierSchema = z.enum([
  "BEST_PATIENT_POPULATION",
  "SECONDARY_PATIENT_POPULATION",
  "EXCLUDED_LOW_LIKELIHOOD_POPULATION",
]);
export type PopulationTier = z.infer<typeof PopulationTierSchema>;

export const PopulationRecommendationSchema = z.object({
  tier: PopulationTierSchema,
  name: z.string(),
  description: z.string(),
  disease_subtype: z.string(),
  mutation: z.string().nullable().optional(),
  expression: z.string().nullable().optional(),
  amplification: z.string().nullable().optional(),
  protein_expression: z.string().nullable().optional(),
  biomarker: z.string(),
  line_of_therapy: z.string(),
  prior_therapy: z.array(z.string()).default([]),
  resistance_state: z.string().nullable().optional(),
  cns_status: z.string(),
  mechanistic_rationale: z.string(),
  evidence_summary: z.string(),
  evidence_citations: z.array(z.record(z.string(), z.unknown())).default([]),
});
export type PopulationRecommendation = z.infer<typeof PopulationRecommendationSchema>;

export const BiomarkerStrategySchema = z.object({
  primary_biomarker: z.string(),
  assay_modality: z.string(),
  stratification_hypothesis: z.string(),
  feasibility: z.string(),
  companion_diagnostic: z.string().nullable().optional(),
  co_testing_requirements: z.array(z.string()).default([]),
});
export type BiomarkerStrategy = z.infer<typeof BiomarkerStrategySchema>;

export const AssetPatientMatchProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  best_patient_population: PopulationRecommendationSchema,
  secondary_patient_population: PopulationRecommendationSchema,
  excluded_patient_population: PopulationRecommendationSchema,
  biomarker_strategy: BiomarkerStrategySchema,
  patient_match_score: z.number().min(0).max(100),
  confidence: z.number().min(0).max(1),
  mechanism: z.string(),
  disclaimer: z.string().default(
    "Do not make patient-specific medical recommendations. This is drug-development population intelligence."
  ),
  evaluated_at: z.string().datetime().optional(),
});
export type AssetPatientMatchProfile = z.infer<typeof AssetPatientMatchProfileSchema>;

export const PatientCohortQuerySchema = z.object({
  disease_subtype: z.string(),
  mutation: z.string().nullable().optional(),
  expression: z.string().nullable().optional(),
  amplification: z.string().nullable().optional(),
  protein_expression: z.string().nullable().optional(),
  biomarker: z.string().nullable().optional(),
  prior_therapy: z.array(z.string()).default([]),
  resistance_state: z.string().nullable().optional(),
  line_of_therapy: z.string().nullable().optional(),
  cns_status: z.string().nullable().optional(),
});
export type PatientCohortQuery = z.infer<typeof PatientCohortQuerySchema>;

export const CandidateAssetMatchRankSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  match_score: z.number().min(0).max(100),
  rank: z.number().int().positive(),
  population_fit: z.string(),
  mechanistic_synergy: z.string(),
  recommended_combination: z.string().nullable().optional(),
  evidence_citations: z.array(z.string()).default([]),
});
export type CandidateAssetMatchRank = z.infer<typeof CandidateAssetMatchRankSchema>;

export const PatientMatchScenarioResponseSchema = z.object({
  query: PatientCohortQuerySchema,
  best_matched_asset: AssetPatientMatchProfileSchema,
  ranked_candidates: z.array(CandidateAssetMatchRankSchema).default([]),
  interpretation: z.string(),
  disclaimer: z.string().default(
    "Do not make patient-specific medical recommendations. This is drug-development population intelligence."
  ),
  evaluated_at: z.string().datetime().optional(),
});
export type PatientMatchScenarioResponse = z.infer<typeof PatientMatchScenarioResponseSchema>;
