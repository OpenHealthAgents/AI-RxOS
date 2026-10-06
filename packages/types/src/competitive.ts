import { z } from "zod";

export const CompetitiveDensityTierSchema = z.enum([
  "LOW",
  "MODERATE",
  "HIGH",
  "VERY_HIGH",
]);
export type CompetitiveDensityTier = z.infer<typeof CompetitiveDensityTierSchema>;

export const DifferentiationTierSchema = z.enum([
  "HIGHLY_DIFFERENTIATED",
  "MODERATELY_DIFFERENTIATED",
  "MINIMALLY_DIFFERENTIATED",
  "UNDIFFERENTIATED",
]);
export type DifferentiationTier = z.infer<typeof DifferentiationTierSchema>;

export const CompetitiveRiskTierSchema = z.enum([
  "LOW",
  "MODERATE",
  "HIGH",
  "CRITICAL",
]);
export type CompetitiveRiskTier = z.infer<typeof CompetitiveRiskTierSchema>;

export const ComparisonAdvantagePolaritySchema = z.enum([
  "FAVORABLE",
  "PARITY",
  "UNFAVORABLE",
]);
export type ComparisonAdvantagePolarity = z.infer<typeof ComparisonAdvantagePolaritySchema>;

export const CompetitorSummarySchema = z.object({
  competitor_id: z.string(),
  name: z.string(),
  sponsor_or_owner: z.string(),
  stage: z.string(),
  modality: z.string(),
  target: z.string(),
  mechanism: z.string(),
  is_approved_soc: z.boolean().default(false),
  is_clinical_stage: z.boolean().default(false),
  is_emerging_academic: z.boolean().default(false),
  primary_indication: z.string(),
  biomarkers: z.array(z.string()).default([]),
  patient_populations: z.array(z.string()).default([]),
  shared_attributes: z.array(z.string()).default([]),
  brief_profile: z.string(),
});
export type CompetitorSummary = z.infer<typeof CompetitorSummarySchema>;

export const CompetitorCohortBreakdownSchema = z.object({
  direct_competitors: z.array(CompetitorSummarySchema).default([]),
  same_target: z.array(CompetitorSummarySchema).default([]),
  same_mechanism: z.array(CompetitorSummarySchema).default([]),
  same_biomarker: z.array(CompetitorSummarySchema).default([]),
  same_indication: z.array(CompetitorSummarySchema).default([]),
  same_patient_population: z.array(CompetitorSummarySchema).default([]),
  same_modality: z.array(CompetitorSummarySchema).default([]),
  clinical_stage_competitors: z.array(CompetitorSummarySchema).default([]),
  approved_standards_of_care: z.array(CompetitorSummarySchema).default([]),
  emerging_academic_programs: z.array(CompetitorSummarySchema).default([]),
});
export type CompetitorCohortBreakdown = z.infer<typeof CompetitorCohortBreakdownSchema>;

export const DimensionComparisonSchema = z.object({
  dimension_name: z.string(),
  focal_value: z.string(),
  competitor_value: z.string(),
  polarity: ComparisonAdvantagePolaritySchema,
  advantage_delta_score: z.number().min(-10).max(10),
  rationale: z.string(),
});
export type DimensionComparison = z.infer<typeof DimensionComparisonSchema>;

export const HeadToHeadComparisonSchema = z.object({
  competitor_id: z.string(),
  competitor_name: z.string(),
  competitor_stage: z.string(),
  is_approved_soc: z.boolean(),
  overall_advantage: ComparisonAdvantagePolaritySchema,
  composite_advantage_score: z.number().min(-100).max(100),
  potency: DimensionComparisonSchema,
  selectivity: DimensionComparisonSchema,
  cns: DimensionComparisonSchema,
  clinical_stage: DimensionComparisonSchema,
  efficacy: DimensionComparisonSchema,
  safety: DimensionComparisonSchema,
  biomarker: DimensionComparisonSchema,
  resistance: DimensionComparisonSchema,
  combination: DimensionComparisonSchema,
  ownership: DimensionComparisonSchema,
  commercial_opportunity: DimensionComparisonSchema,
  key_differentiators: z.array(z.string()).default([]),
  competitive_threat_level: z.string(),
  summary: z.string(),
});
export type HeadToHeadComparison = z.infer<typeof HeadToHeadComparisonSchema>;

export const CompetitiveDensityEvaluationSchema = z.object({
  density_score: z.number().min(0).max(100),
  density_tier: CompetitiveDensityTierSchema,
  total_competitors_count: z.number().int().nonnegative(),
  direct_competitors_count: z.number().int().nonnegative(),
  clinical_competitors_count: z.number().int().nonnegative(),
  approved_soc_count: z.number().int().nonnegative(),
  academic_programs_count: z.number().int().nonnegative(),
  stage_distribution: z.record(z.string(), z.number()).default({}),
  modality_distribution: z.record(z.string(), z.number()).default({}),
  crowding_assessment: z.string(),
  density_formula: z.string(),
});
export type CompetitiveDensityEvaluation = z.infer<typeof CompetitiveDensityEvaluationSchema>;

export const DifferentiationEvaluationSchema = z.object({
  differentiation_score: z.number().min(0).max(100),
  differentiation_tier: DifferentiationTierSchema,
  key_usps: z.array(z.string()).default([]),
  clinical_moat: z.string(),
  vulnerabilities: z.array(z.string()).default([]),
  differentiation_formula: z.string(),
});
export type DifferentiationEvaluation = z.infer<typeof DifferentiationEvaluationSchema>;

export const CompetitiveRiskEvaluationSchema = z.object({
  risk_score: z.number().min(0).max(100),
  risk_tier: CompetitiveRiskTierSchema,
  primary_threats: z.array(z.string()).default([]),
  soc_displacement_barrier: z.string(),
  displacement_scenarios: z.array(z.string()).default([]),
  mitigation_strategies: z.array(z.string()).default([]),
  risk_formula: z.string(),
});
export type CompetitiveRiskEvaluation = z.infer<typeof CompetitiveRiskEvaluationSchema>;

export const WhiteSpaceOpportunityRecordSchema = z.object({
  opportunity_id: z.string(),
  niche_name: z.string(),
  target_patient_population: z.string(),
  unmet_clinical_need: z.string(),
  mechanistic_or_clinical_gap: z.string(),
  competitive_intensity: z.string(),
  commercial_attractiveness: z.string(),
  recommended_development_action: z.string(),
});
export type WhiteSpaceOpportunityRecord = z.infer<typeof WhiteSpaceOpportunityRecordSchema>;

export const CompetitiveIntelligenceProfileSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string(),
  asset_name: z.string(),
  target: z.string(),
  primary_indication: z.string(),
  patient_population: z.string(),
  modality: z.string(),
  stage: z.string(),
  cohorts: CompetitorCohortBreakdownSchema,
  head_to_head_comparisons: z.array(HeadToHeadComparisonSchema).default([]),
  competitive_density: CompetitiveDensityEvaluationSchema,
  differentiation: DifferentiationEvaluationSchema,
  competitive_risk: CompetitiveRiskEvaluationSchema,
  white_space_opportunities: z.array(WhiteSpaceOpportunityRecordSchema).default([]),
  evidence_citations: z.array(z.string()).default([]),
  created_at: z.string().datetime(),
});
export type CompetitiveIntelligenceProfile = z.infer<typeof CompetitiveIntelligenceProfileSchema>;

export const EvaluateCompetitiveRequestSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string().optional(),
  target: z.string().default("HER2"),
  indication: z.string().default("Non-Small Cell Lung Cancer"),
  patient_population: z.string().default("Pretreated HER2-mutant oncology"),
  modality: z.string().default("Small Molecule TKI"),
  stage: z.string().default("Phase II"),
});
export type EvaluateCompetitiveRequest = z.infer<typeof EvaluateCompetitiveRequestSchema>;
