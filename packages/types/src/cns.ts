import { z } from "zod";

export const CNSEvidenceLevelSchema = z.enum([
  "direct_measurement",
  "animal_evidence",
  "in_vitro_inference",
  "mechanistic_inference",
  "clinical_cns_evidence",
]);
export type CNSEvidenceLevel = z.infer<typeof CNSEvidenceLevelSchema>;

export const CNSSpeciesSchema = z.enum([
  "human",
  "mouse",
  "rat",
  "cynomolgus",
  "in_vitro",
]);
export type CNSSpecies = z.infer<typeof CNSSpeciesSchema>;

export const CNSParameterTypeSchema = z.enum([
  "brain_plasma_ratio_kp",
  "kp_uu",
  "csf_exposure",
  "unbound_brain_concentration",
  "bbb_penetration",
  "brain_tumor_exposure",
  "intracranial_response",
  "cns_progression",
  "brain_metastasis_response",
]);
export type CNSParameterType = z.infer<typeof CNSParameterTypeSchema>;

export const RawCNSObservationSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string(),
  parameter_type: CNSParameterTypeSchema,
  evidence_level: CNSEvidenceLevelSchema,
  species: CNSSpeciesSchema,
  experimental_condition: z.string().nullable().optional(),
  raw_text_value: z.string(),
  normalized_value: z.number(),
  normalized_unit: z.string().nullable().optional(),
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  pmid: z.string().nullable().optional(),
  nct_id: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1).default(1.0),
  observation_date: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type RawCNSObservation = z.infer<typeof RawCNSObservationSchema>;

export const NormalizedCNSParameterSchema = z.object({
  parameter_type: CNSParameterTypeSchema,
  normalized_value: z.number(),
  normalized_unit: z.string(),
  evidence_level: CNSEvidenceLevelSchema,
  species: CNSSpeciesSchema,
  raw_observation_ids: z.array(z.string().uuid()).default([]),
  citations: z.array(z.string()).default([]),
  interpretation: z.string(),
});
export type NormalizedCNSParameter = z.infer<typeof NormalizedCNSParameterSchema>;

export const CNSScoreLineageSchema = z.object({
  score_name: z.string(),
  formula: z.string(),
  inputs: z.record(z.string(), z.unknown()),
  raw_observation_ids: z.array(z.string().uuid()).default([]),
  calculated_value: z.number(),
  evidence_level_contributions: z.record(z.string(), z.number()).default({}),
  evidence_gaps: z.array(z.string()).default([]),
});
export type CNSScoreLineage = z.infer<typeof CNSScoreLineageSchema>;

export const CNSIntelligenceProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  cns_exposure_score: z.number().min(0).max(100),
  cns_activity_score: z.number().min(0).max(100),
  cns_translational_confidence: z.number().min(0).max(1),
  normalized_parameters: z.record(z.string(), NormalizedCNSParameterSchema).default({}),
  raw_observations: z.array(RawCNSObservationSchema).default([]),
  lineages: z.record(z.string(), CNSScoreLineageSchema).default({}),
  evidence_levels_present: z.array(CNSEvidenceLevelSchema).default([]),
  clinical_cns_efficacy_inferred_solely_from_physicochemical: z.boolean().default(false),
  unknowns: z.array(z.string()).default([]),
  evaluated_at: z.string().datetime().optional(),
});
export type CNSIntelligenceProfile = z.infer<typeof CNSIntelligenceProfileSchema>;

export const EvaluateAssetCNSRequestSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string().nullable().optional(),
  custom_observations: z.array(RawCNSObservationSchema).nullable().optional(),
});
export type EvaluateAssetCNSRequest = z.infer<typeof EvaluateAssetCNSRequestSchema>;

export const EvaluateAssetCNSResponseSchema = z.object({
  profile: CNSIntelligenceProfileSchema,
});
export type EvaluateAssetCNSResponse = z.infer<typeof EvaluateAssetCNSResponseSchema>;
