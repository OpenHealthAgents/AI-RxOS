import { z } from "zod";

export const CombinationValidationStatusSchema = z.enum([
  "clinically validated",
  "preclinical supported",
  "mechanistically plausible",
  "AI-generated hypothesis",
]);
export type CombinationValidationStatus = z.infer<typeof CombinationValidationStatusSchema>;

export const DevelopmentRiskTierSchema = z.enum([
  "LOW",
  "MODERATE",
  "HIGH",
  "CRITICAL",
]);
export type DevelopmentRiskTier = z.infer<typeof DevelopmentRiskTierSchema>;

export const ToxicityOverlapSeveritySchema = z.enum([
  "MINIMAL",
  "MANAGEABLE",
  "SIGNIFICANT",
  "SEVERE",
]);
export type ToxicityOverlapSeverity = z.infer<typeof ToxicityOverlapSeveritySchema>;

export const MechanisticComplementarityEvaluationSchema = z.object({
  synergy_mechanism: z.string(),
  biological_rationale: z.string(),
  pathway_target: z.string(),
  escape_suppression_mode: z.string(),
});
export type MechanisticComplementarityEvaluation = z.infer<typeof MechanisticComplementarityEvaluationSchema>;

export const PreclinicalEvidenceEvaluationSchema = z.object({
  in_vitro_synergy: z.string().nullable().optional(),
  in_vivo_models: z.array(z.string()).default([]),
  tumor_growth_inhibition_pct: z.number().nullable().optional(),
  summary: z.string(),
});
export type PreclinicalEvidenceEvaluation = z.infer<typeof PreclinicalEvidenceEvaluationSchema>;

export const ClinicalEvidenceEvaluationSchema = z.object({
  trial_phase: z.string().nullable().optional(),
  nct_id: z.string().nullable().optional(),
  reported_orr_pct: z.number().nullable().optional(),
  reported_pfs_months: z.number().nullable().optional(),
  summary: z.string(),
  citations: z.array(z.record(z.string(), z.any())).default([]),
});
export type ClinicalEvidenceEvaluation = z.infer<typeof ClinicalEvidenceEvaluationSchema>;

export const ToxicityOverlapEvaluationSchema = z.object({
  overlap_severity: ToxicityOverlapSeveritySchema,
  shared_adverse_events: z.array(z.string()).default([]),
  dose_limiting_toxicities: z.array(z.string()).default([]),
  therapeutic_window_impact: z.string(),
  mitigation_strategy: z.string(),
});
export type ToxicityOverlapEvaluation = z.infer<typeof ToxicityOverlapEvaluationSchema>;

export const PharmacologicalFeasibilityEvaluationSchema = z.object({
  cyp_interaction_risk: z.string(),
  efflux_interaction: z.string(),
  schedule_compatibility: z.string(),
  pk_ddi_score: z.number().min(0).max(1),
});
export type PharmacologicalFeasibilityEvaluation = z.infer<typeof PharmacologicalFeasibilityEvaluationSchema>;

export const DevelopmentFeasibilityEvaluationSchema = z.object({
  sponsor_landscape: z.string(),
  regulatory_pathway: z.string(),
  ip_freedom: z.string(),
  feasibility_score: z.number().min(0).max(1),
});
export type DevelopmentFeasibilityEvaluation = z.infer<typeof DevelopmentFeasibilityEvaluationSchema>;

export const ExistingCombinationReferenceSchema = z.object({
  regimen_name: z.string(),
  indication: z.string(),
  status: z.string(),
  reference: z.string(),
});
export type ExistingCombinationReference = z.infer<typeof ExistingCombinationReferenceSchema>;

export const CompetitiveCombinationReferenceSchema = z.object({
  competitor_name: z.string(),
  competing_regimen: z.string(),
  phase: z.string(),
  differentiation: z.string(),
});
export type CompetitiveCombinationReference = z.infer<typeof CompetitiveCombinationReferenceSchema>;

export const RecommendedCombinationStrategySchema = z.object({
  id: z.string(),
  regimen_name: z.string(),
  primary_asset_id: z.string(),
  primary_asset_name: z.string(),
  partner_name: z.string(),
  partner_class: z.string(),
  resistance_mechanism_addressed: z.string(),
  resistance_category: z.string(),
  validation_status: CombinationValidationStatusSchema,
  is_clinically_validated: z.boolean().default(false),
  mechanistic_complementarity: MechanisticComplementarityEvaluationSchema,
  preclinical_evidence: PreclinicalEvidenceEvaluationSchema,
  clinical_evidence: ClinicalEvidenceEvaluationSchema,
  toxicity_overlap: ToxicityOverlapEvaluationSchema,
  pharmacological_feasibility: PharmacologicalFeasibilityEvaluationSchema,
  development_feasibility: DevelopmentFeasibilityEvaluationSchema,
  existing_combinations: z.array(ExistingCombinationReferenceSchema).default([]),
  competitive_combinations: z.array(CompetitiveCombinationReferenceSchema).default([]),
  rationale: z.string(),
  evidence_citations: z.array(z.record(z.string(), z.any())).default([]),
  confidence: z.number().min(0).max(1),
  development_risk_score: z.number().min(0).max(100),
  development_risk_tier: DevelopmentRiskTierSchema,
  epistemic_disclaimer: z.string(),
});
export type RecommendedCombinationStrategy = z.infer<typeof RecommendedCombinationStrategySchema>;

export const CombinationIntelligenceProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  primary_combination: RecommendedCombinationStrategySchema,
  recommended_combinations: z.array(RecommendedCombinationStrategySchema),
  epistemic_audit: z.record(z.string(), z.any()).default({}),
  disclaimer: z.string(),
  evaluated_at: z.string().datetime().or(z.date()),
});
export type CombinationIntelligenceProfile = z.infer<typeof CombinationIntelligenceProfileSchema>;

export const EvaluateCombinationQuerySchema = z.object({
  asset_id: z.string().optional(),
  resistance_mechanism: z.string().optional(),
  min_confidence: z.number().min(0).max(1).default(0.0),
  max_risk_tier: DevelopmentRiskTierSchema.optional(),
  include_ai_generated: z.boolean().default(true),
});
export type EvaluateCombinationQuery = z.infer<typeof EvaluateCombinationQuerySchema>;
