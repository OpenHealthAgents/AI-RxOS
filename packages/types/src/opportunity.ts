import { z } from "zod";

export const StrategicActionSchema = z.enum([
  "PURSUE",
  "INVESTIGATE",
  "PARTNER",
  "LICENSE",
  "MONITOR",
  "AVOID",
]);
export type StrategicAction = z.infer<typeof StrategicActionSchema>;

export const DevelopmentStageSchema = z.enum([
  "Preclinical",
  "IND-enabling",
  "Phase I",
  "Phase Ib",
  "Phase II",
  "Phase II/III",
  "Phase III",
  "Regulatory review",
  "Approved",
  "Withdrawn",
  "Terminated",
  "Discontinued",
]);
export type DevelopmentStage = z.infer<typeof DevelopmentStageSchema>;

export const EvidencePolaritySchema = z.enum([
  "SUPPORTING",
  "CONTRADICTING",
  "CONTRADICTORY",
  "NEUTRAL",
  "UNKNOWN",
]);
export type EvidencePolarity = z.infer<typeof EvidencePolaritySchema>;

export const EvidenceItemSchema = z.object({
  id: z.string(),
  source_type: z.enum([
    "literature",
    "clinical_trial",
    "fda_label",
    "regulatory_authority",
    "patent",
    "conference_abstract",
  ]),
  source_ref: z.string(),
  title: z.string(),
  citation: z.string(),
  publication_year: z.number().int(),
  url: z.string().nullable().optional(),
  excerpt: z.string(),
  polarity: EvidencePolaritySchema.default("SUPPORTING"),
  is_verified: z.boolean().default(true),
  as_of_date: z.string(),
});
export type EvidenceItem = z.infer<typeof EvidenceItemSchema>;

export const StageTransitionProbabilitiesSchema = z.object({
  preclinical_to_ind: z.number(),
  phase_i_to_ii: z.number(),
  phase_ii_to_iii: z.number(),
  phase_iii_to_approval: z.number(),
  model_version: z.string().default("Model v0.1"),
  calibration_note: z.string().optional(),
});
export type StageTransitionProbabilities = z.infer<typeof StageTransitionProbabilitiesSchema>;

export const BiologyProfileMetricsSchema = z.object({
  target_selectivity: z.number(),
  potency: z.number(),
  safety_ti: z.number(),
  clinical_readiness: z.number(),
  biomarker_strategy: z.number(),
  cns_potential: z.number(),
});
export type BiologyProfileMetrics = z.infer<typeof BiologyProfileMetricsSchema>;

export const ResistanceMechanismSchema = z.object({
  name: z.string(),
  impact: z.enum(["High", "Moderate", "Low"]),
  is_predicted: z.boolean().default(false),
  description: z.string(),
  evidence_ids: z.array(z.string()).default([]),
});
export type ResistanceMechanism = z.infer<typeof ResistanceMechanismSchema>;

export const RecommendedCombinationSchema = z.object({
  partner_name: z.string(),
  synergy_type: z.string(),
  rationale: z.string(),
  clinical_status: z.string(),
  evidence_ids: z.array(z.string()).default([]),
});
export type RecommendedCombination = z.infer<typeof RecommendedCombinationSchema>;

export const SafetyToxicityProfileSchema = z.object({
  common_aes: z.string(),
  dose_limiting_toxicities: z.string(),
  therapeutic_index: z.string(),
  discontinuation_rate: z.string(),
  cardiac_risk: z.string().optional(),
  gi_toxicity_grade: z.enum(["Mild", "Low-Moderate", "Moderate", "High"]).default("Low-Moderate"),
  safety_score: z.number(),
});
export type SafetyToxicityProfile = z.infer<typeof SafetyToxicityProfileSchema>;

export const PatientMatchProfileSchema = z.object({
  best_patient_population: z.array(z.string()),
  biomarkers: z.array(z.string()),
  setting: z.string().default("Metastatic"),
  prior_lines: z.string(),
  cns_metastases_benefit: z.boolean().default(true),
  match_score_formula_lineage: z.string().optional(),
});
export type PatientMatchProfile = z.infer<typeof PatientMatchProfileSchema>;

export const BusinessCompetitiveProfileSchema = z.object({
  current_owner: z.string(),
  patent_ip: z.string(),
  commercial_opportunity: z.string(),
  competitive_assets: z.string(),
  licensing_partnering_feasibility: z.string(),
  fto_legal_disclaimer: z.string(),
});
export type BusinessCompetitiveProfile = z.infer<typeof BusinessCompetitiveProfileSchema>;

export const DecisionRecommendationSchema = z.object({
  action: StrategicActionSchema,
  badge_text: z.string(),
  rationale: z.string(),
  confidence: z.number(),
  development_potential_score: z.number(),
  development_potential_tier: z.enum(["Very Low", "Low", "Moderate", "High", "Very High"]),
  model_lineage: z.string().optional(),
});
export type DecisionRecommendation = z.infer<typeof DecisionRecommendationSchema>;

export const UnknownFactorSchema = z.object({
  id: z.string(),
  category: z.enum(["Clinical Efficacy", "Toxicity", "Biomarker", "IP / Licensing", "Commercial"]),
  question: z.string(),
  current_gap: z.string(),
  suggested_study: z.string(),
});
export type UnknownFactor = z.infer<typeof UnknownFactorSchema>;

export const AssetIntelligenceSchema = z.object({
  id: z.string(),
  name: z.string(),
  code_name: z.string().nullable().optional(),
  target: z.string().default("HER2"),
  modality: z.string(),
  stage: DevelopmentStageSchema,
  status_label: z.enum(["Investigational", "Approved", "Preclinical", "Terminated"]).default("Investigational"),
  owner: z.string(),
  primary_indication: z.string(),
  key_attributes: z.record(z.string(), z.string()),
  biology_profile: BiologyProfileMetricsSchema,
  stage_transitions: StageTransitionProbabilitiesSchema,
  resistance_mechanisms: z.array(ResistanceMechanismSchema),
  combinations: z.array(RecommendedCombinationSchema),
  safety_profile: SafetyToxicityProfileSchema,
  patient_match: PatientMatchProfileSchema,
  business_profile: BusinessCompetitiveProfileSchema,
  recommendation: DecisionRecommendationSchema,
  supporting_evidence: z.array(EvidenceItemSchema),
  contradicting_evidence: z.array(EvidenceItemSchema),
  unknowns: z.array(UnknownFactorSchema),
  ai_inferences: z.array(z.string()).default([]),
  last_updated: z.string().default("2026-10-01"),
});
export type AssetIntelligence = z.infer<typeof AssetIntelligenceSchema>;

export const AssetComparisonResultSchema = z.object({
  target: z.string(),
  indication: z.string(),
  setting: z.string(),
  assets: z.array(AssetIntelligenceSchema),
  comparison_summary: z.string(),
  key_differentiators: z.array(z.string()),
  head_to_head_advantages: z.record(z.string(), z.array(z.string())),
  recommendation_summary: z.record(z.string(), z.string()),
});
export type AssetComparisonResult = z.infer<typeof AssetComparisonResultSchema>;

export const HistoricalBacktestResultSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  cutoff_date: z.string(),
  evidence_items_eligible: z.number(),
  evidence_items_suppressed_future: z.number(),
  predicted_action_at_cutoff: StrategicActionSchema,
  predicted_transition_probabilities: StageTransitionProbabilitiesSchema,
  predicted_development_potential: z.number(),
  historical_recommendation_rationale: z.string(),
  ground_truth_eventual_outcome: z.string(),
  prediction_accuracy: z.enum(["True Positive", "True Negative", "Calibrated Success", "Consistent Divergence"]),
  anti_leakage_audit_passed: z.boolean(),
});
export type HistoricalBacktestResult = z.infer<typeof HistoricalBacktestResultSchema>;

export const ScientificEvidenceStateSchema = z.enum([
  "positive",
  "negative",
  "neutral",
  "unknown",
  "insufficient_evidence",
  "conflicting_evidence",
  "ai_inference",
  "verified_fact",
]);
export type ScientificEvidenceState = z.infer<typeof ScientificEvidenceStateSchema>;

export const ScientificPrioritySchema = z.enum([
  "critical",
  "high",
  "moderate",
  "low",
  "monitoring",
]);
export type ScientificPriority = z.infer<typeof ScientificPrioritySchema>;

export const ScientificMilestoneSchema = z.object({
  id: z.string(),
  date: z.string(),
  title: z.string(),
  category: z.enum(["trial", "regulatory", "preclinical", "patent", "deal"]),
  status: z.enum(["completed", "in_progress", "projected"]),
  description: z.string().optional(),
  evidence_id: z.string().optional(),
});
export type ScientificMilestone = z.infer<typeof ScientificMilestoneSchema>;

