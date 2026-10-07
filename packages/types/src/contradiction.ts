import { z } from "zod";
import {
  EvidenceQualitySchema,
  EvidenceQuality,
  EvidenceConfidenceSchema,
  EvidenceConfidence,
  StudyDesignTypeSchema,
  StudyDesignType,
  EvidenceSourceSchema,
  EvidenceSource,
} from "./evidence";
import {
  EvidencePolaritySchema,
  EvidencePolarity,
} from "./opportunity";

// ==============================================================================
// 1. Contradictory Claim Schema
// ==============================================================================

export const ContradictoryClaimSchema = z.object({
  id: z.string().uuid(),
  claim_text: z.string(),
  polarity: EvidencePolaritySchema,
  source: EvidenceSourceSchema,
  date: z.string(), // ISO date
  study_design: StudyDesignTypeSchema,
  quality: EvidenceQualitySchema,
  confidence: EvidenceConfidenceSchema,
  numeric_measurement: z.string().nullable().optional(),
  observed_endpoint: z.string().nullable().optional(),
  sample_size: z.number().int().nullable().optional(),
});
export type ContradictoryClaim = z.infer<typeof ContradictoryClaimSchema>;

// ==============================================================================
// 2. Disagreement Category
// ==============================================================================

export const DisagreementCategorySchema = z.enum([
  "efficacy_divergence",
  "safety_toxicity_conflict",
  "cns_penetration_discrepancy",
  "resistance_emergence_divergence",
  "selectivity_margin_dispute",
  "biomarker_stratification_discordance",
]);
export type DisagreementCategory = z.infer<typeof DisagreementCategorySchema>;

export const DisagreementResolutionStatusSchema = z.enum([
  "unresolved_dispute",
  "partially_explained",
  "resolved_by_superior_design",
  "under_active_investigation",
]);
export type DisagreementResolutionStatus = z.infer<typeof DisagreementResolutionStatusSchema>;

// ==============================================================================
// 3. Contradiction Record
// ==============================================================================

export const ContradictionRecordSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  topic: z.string(),
  parameter_name: z.string(),
  category: DisagreementCategorySchema,
  status: DisagreementResolutionStatusSchema.default("unresolved_dispute"),
  claim_a: ContradictoryClaimSchema,
  claim_b: ContradictoryClaimSchema,
  possible_explanation: z.string(),
  epistemic_warning: z.string(),
  resolution_recommendation: z.string(),
  quality_delta: z.number(),
  confidence_delta: z.number(),
  created_at: z.string().datetime().optional(),
});
export type ContradictionRecord = z.infer<typeof ContradictionRecordSchema>;

export const ContradictionReportSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  total_contradictions: z.number().int(),
  has_unresolved_disputes: z.boolean(),
  contradictions: z.array(ContradictionRecordSchema),
  epistemic_disclaimer: z.string(),
});
export type ContradictionReport = z.infer<typeof ContradictionReportSchema>;
