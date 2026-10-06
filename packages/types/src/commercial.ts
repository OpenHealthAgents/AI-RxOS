import { z } from "zod";

export const AssumptionProvenanceSchema = z.enum([
  "Observed",
  "Externally sourced",
  "Modeled",
  "Assumed",
  "Unknown",
]);
export type AssumptionProvenance = z.infer<typeof AssumptionProvenanceSchema>;

export const MarketAttractivenessTierSchema = z.enum([
  "VERY_HIGH",
  "HIGH",
  "MODERATE",
  "LOW",
  "NICHE",
]);
export type MarketAttractivenessTier = z.infer<typeof MarketAttractivenessTierSchema>;

export const CompetitivePressureTierSchema = z.enum([
  "INTENSE",
  "HIGH",
  "MODERATE",
  "LOW",
]);
export type CompetitivePressureTier = z.infer<typeof CompetitivePressureTierSchema>;

export const CommercialUnmetNeedTierSchema = z.enum([
  "CRITICAL",
  "HIGH",
  "MODERATE",
  "LOW",
]);
export type CommercialUnmetNeedTier = z.infer<typeof CommercialUnmetNeedTierSchema>;

export const CommercialAssumptionRecordSchema = z.object({
  key: z.string(),
  parameter_label: z.string(),
  parameter_value: z.string(),
  provenance: AssumptionProvenanceSchema,
  source_citation: z.string(),
  methodology: z.string(),
  confidence: z.number().min(0).max(1),
});
export type CommercialAssumptionRecord = z.infer<typeof CommercialAssumptionRecordSchema>;

export const AddressablePopulationEvaluationSchema = z.object({
  annual_incidence_us: z.number().int().nonnegative(),
  annual_incidence_eu5: z.number().int().nonnegative(),
  annual_incidence_jp: z.number().int().nonnegative(),
  metastatic_advanced_rate_pct: z.number().min(0).max(100),
  total_metastatic_pool: z.number().int().nonnegative(),
  provenance: AssumptionProvenanceSchema,
  source_citation: z.string(),
  methodology: z.string(),
});
export type AddressablePopulationEvaluation = z.infer<typeof AddressablePopulationEvaluationSchema>;

export const BiomarkerDefinedPopulationEvaluationSchema = z.object({
  biomarker_name: z.string(),
  biomarker_prevalence_pct: z.number().min(0).max(100),
  testing_penetration_rate_pct: z.number().min(0).max(100),
  target_eligible_patient_pool: z.number().int().nonnegative(),
  provenance: AssumptionProvenanceSchema,
  source_citation: z.string(),
  calculation_formula: z.string(),
});
export type BiomarkerDefinedPopulationEvaluation = z.infer<typeof BiomarkerDefinedPopulationEvaluationSchema>;

export const TreatmentDurationEvaluationSchema = z.object({
  median_pfs_months: z.number().nonnegative(),
  median_duration_of_treatment_months: z.number().nonnegative(),
  treatment_cycles_annual_equivalent: z.number().nonnegative(),
  compliance_persistence_rate_pct: z.number().min(0).max(100),
  provenance: AssumptionProvenanceSchema,
  source_citation: z.string(),
});
export type TreatmentDurationEvaluation = z.infer<typeof TreatmentDurationEvaluationSchema>;

export const StandardOfCareEvaluationSchema = z.object({
  soc_regimen_name: z.string(),
  soc_efficacy_benchmark: z.string(),
  soc_shortcomings: z.array(z.string()).default([]),
  soc_market_share_pct: z.number().min(0).max(100),
  provenance: AssumptionProvenanceSchema,
  source_citation: z.string(),
});
export type StandardOfCareEvaluation = z.infer<typeof StandardOfCareEvaluationSchema>;

export const UnmetNeedEvaluationSchema = z.object({
  unmet_need_score: z.number().min(0).max(100),
  unmet_need_tier: CommercialUnmetNeedTierSchema,
  drivers: z.array(z.string()).default([]),
  post_progression_prognosis: z.string(),
  provenance: AssumptionProvenanceSchema,
  source_citation: z.string(),
});
export type UnmetNeedEvaluation = z.infer<typeof UnmetNeedEvaluationSchema>;

export const CommercialCompetitiveDensityEvaluationSchema = z.object({
  density_score: z.number().min(0).max(100),
  active_commercial_competitors_count: z.number().int().nonnegative(),
  pipeline_competitors_count: z.number().int().nonnegative(),
  crowding_summary: z.string(),
  provenance: AssumptionProvenanceSchema,
});
export type CommercialCompetitiveDensityEvaluation = z.infer<typeof CommercialCompetitiveDensityEvaluationSchema>;

export const ClinicalDifferentiationEvaluationSchema = z.object({
  differentiation_score: z.number().min(0).max(100),
  key_differentiators: z.array(z.string()).default([]),
  commercial_moat: z.string(),
  provenance: AssumptionProvenanceSchema,
});
export type ClinicalDifferentiationEvaluation = z.infer<typeof ClinicalDifferentiationEvaluationSchema>;

export const PotentialLineOfTherapyEvaluationSchema = z.object({
  initial_target_line: z.string(),
  potential_expansion_line: z.string(),
  nccn_guideline_positioning_goal: z.string(),
  rationale: z.string(),
  provenance: AssumptionProvenanceSchema,
});
export type PotentialLineOfTherapyEvaluation = z.infer<typeof PotentialLineOfTherapyEvaluationSchema>;

export const PricingAnalogsEvaluationSchema = z.object({
  benchmark_drug_name: z.string(),
  benchmark_modality: z.string(),
  monthly_wac_usd: z.number().nonnegative(),
  annual_gross_treatment_cost_usd: z.number().nonnegative(),
  gross_to_net_discount_pct: z.number().min(0).max(100),
  net_realized_monthly_usd: z.number().nonnegative(),
  provenance: AssumptionProvenanceSchema,
  pricing_source: z.string(),
});
export type PricingAnalogsEvaluation = z.infer<typeof PricingAnalogsEvaluationSchema>;

export const PipelineCrowdingEvaluationSchema = z.object({
  phase_3_threats_count: z.number().int().nonnegative(),
  fast_followers_count: z.number().int().nonnegative(),
  threat_assessment: z.string(),
  leapfrog_risk: z.string(),
  provenance: AssumptionProvenanceSchema,
});
export type PipelineCrowdingEvaluation = z.infer<typeof PipelineCrowdingEvaluationSchema>;

export const MarketExpansionScenarioSchema = z.object({
  scenario_name: z.string(),
  target_indication: z.string(),
  target_line: z.string(),
  incremental_patient_pool: z.number().int().nonnegative(),
  timeline_years: z.number().nonnegative(),
  regulatory_pathway: z.string(),
  peak_penetration_potential_pct: z.number().min(0).max(100),
  estimated_incremental_revenue_usd: z.number().nonnegative(),
  provenance: AssumptionProvenanceSchema,
});
export type MarketExpansionScenario = z.infer<typeof MarketExpansionScenarioSchema>;

export const ModeledRevenueProjectionsSchema = z.object({
  base_peak_share_pct: z.number().min(0).max(100),
  base_peak_sales_usd: z.number().nonnegative(),
  bull_peak_share_pct: z.number().min(0).max(100),
  bull_peak_sales_usd: z.number().nonnegative(),
  bear_peak_share_pct: z.number().min(0).max(100),
  bear_peak_sales_usd: z.number().nonnegative(),
  projected_peak_year: z.number().int(),
  derivation_lineage: z.string(),
});
export type ModeledRevenueProjections = z.infer<typeof ModeledRevenueProjectionsSchema>;

export const CommercialOpportunityProfileSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string(),
  asset_name: z.string(),
  indication: z.string(),
  target: z.string(),
  potential_line_of_therapy: z.string(),
  commercial_opportunity_score: z.number().min(0).max(100),
  market_attractiveness_score: z.number().min(0).max(100),
  market_attractiveness_tier: MarketAttractivenessTierSchema,
  competitive_pressure_score: z.number().min(0).max(100),
  competitive_pressure_tier: CompetitivePressureTierSchema,
  unmet_need_score: z.number().min(0).max(100),
  unmet_need_tier: CommercialUnmetNeedTierSchema,
  commercial_confidence: z.number().min(0).max(1),
  addressable_population: AddressablePopulationEvaluationSchema,
  biomarker_defined_population: BiomarkerDefinedPopulationEvaluationSchema,
  treatment_duration: TreatmentDurationEvaluationSchema,
  standard_of_care: StandardOfCareEvaluationSchema,
  unmet_need: UnmetNeedEvaluationSchema,
  competitive_density: CommercialCompetitiveDensityEvaluationSchema,
  clinical_differentiation: ClinicalDifferentiationEvaluationSchema,
  potential_line_of_therapy_eval: PotentialLineOfTherapyEvaluationSchema,
  pricing_analogs: PricingAnalogsEvaluationSchema,
  pipeline_crowding: PipelineCrowdingEvaluationSchema,
  market_expansion_opportunities: z.array(MarketExpansionScenarioSchema).default([]),
  modeled_revenue_projections: ModeledRevenueProjectionsSchema,
  assumptions_audit: z.array(CommercialAssumptionRecordSchema).default([]),
  has_unknown_assumptions: z.boolean().default(false),
  disclaimer: z.string(),
  created_at: z.string().datetime(),
});
export type CommercialOpportunityProfile = z.infer<typeof CommercialOpportunityProfileSchema>;

export const EvaluateCommercialRequestSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string().optional(),
  target: z.string().default("HER2"),
  indication: z.string().default("Non-Small Cell Lung Cancer"),
  potential_line_of_therapy: z.string().default("2L+ post-platinum / post-ADC"),
});
export type EvaluateCommercialRequest = z.infer<typeof EvaluateCommercialRequestSchema>;
