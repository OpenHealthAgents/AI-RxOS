import { z } from "zod";

export const SafetyRatingSchema = z.enum([
  "GOOD",
  "MODERATE",
  "HIGH RISK",
  "INSUFFICIENT EVIDENCE",
]);
export type SafetyRating = z.infer<typeof SafetyRatingSchema>;

export const OrganSystemSchema = z.enum([
  "GASTROINTESTINAL",
  "HEPATIC",
  "CARDIAC",
  "PULMONARY",
  "DERMATOLOGIC",
  "HEMATOLOGIC",
  "RENAL",
  "NEUROLOGIC",
]);
export type OrganSystem = z.infer<typeof OrganSystemSchema>;

export const ToxicitySeverityGradeSchema = z.enum([
  "Grade 1 (Mild)",
  "Grade 2 (Moderate)",
  "Grade 3 (Severe)",
  "Grade 4 (Life-threatening)",
  "Grade 5 (Fatal)",
]);
export type ToxicitySeverityGrade = z.infer<typeof ToxicitySeverityGradeSchema>;

export const RiskSignalSeveritySchema = z.enum([
  "BLACK_BOX",
  "WARNING",
  "WATCH",
  "INVESTIGATIONAL",
]);
export type RiskSignalSeverity = z.infer<typeof RiskSignalSeveritySchema>;

export const AdverseEventRecordSchema = z.object({
  term: z.string(),
  system_organ_class: OrganSystemSchema,
  any_grade_rate_pct: z.number().min(0).max(100),
  grade_3_plus_rate_pct: z.number().min(0).max(100),
  is_dose_limiting: z.boolean().default(false),
  is_target_related: z.boolean().default(false),
  is_serious: z.boolean().default(false),
  clinical_description: z.string(),
});
export type AdverseEventRecord = z.infer<typeof AdverseEventRecordSchema>;

export const DoseLimitingToxicityEvaluationSchema = z.object({
  dlt_observed: z.boolean(),
  dlt_terms: z.array(z.string()).default([]),
  maximum_tolerated_dose: z.string().nullable().optional(),
  recommended_phase_2_dose: z.string().nullable().optional(),
  project_optimus_compliant: z.boolean(),
  dlt_rate_at_rp2d_pct: z.number().nullable().optional(),
  summary: z.string(),
});
export type DoseLimitingToxicityEvaluation = z.infer<typeof DoseLimitingToxicityEvaluationSchema>;

export const DiscontinuationEvaluationSchema = z.object({
  all_cause_discontinuation_pct: z.number().min(0).max(100),
  ae_related_discontinuation_pct: z.number().min(0).max(100),
  dose_reduction_pct: z.number().min(0).max(100),
  dose_interruption_pct: z.number().min(0).max(100),
  primary_driver_terms: z.array(z.string()).default([]),
  tolerability_impact_summary: z.string(),
});
export type DiscontinuationEvaluation = z.infer<typeof DiscontinuationEvaluationSchema>;

export const OrganToxicityProfileSchema = z.object({
  organ_system: OrganSystemSchema,
  severity_tier: z.string(),
  primary_manifestations: z.array(z.string()).default([]),
  monitoring_requirement: z.string(),
  reversibility: z.string(),
  risk_score: z.number().min(0).max(100),
});
export type OrganToxicityProfile = z.infer<typeof OrganToxicityProfileSchema>;

export const TargetRelatedToxicityEvaluationSchema = z.object({
  target_mechanism: z.string(),
  is_on_target_liability: z.boolean(),
  selectivity_ratio_vs_offtarget: z.number().nullable().optional(),
  selectivity_protective_effect: z.string(),
  on_target_mitigation: z.string(),
});
export type TargetRelatedToxicityEvaluation = z.infer<typeof TargetRelatedToxicityEvaluationSchema>;

export const OffTargetToxicityEvaluationSchema = z.object({
  promiscuity_index: z.number().min(0).max(1),
  off_target_kinases_inhibited: z.array(z.string()).default([]),
  hERG_inhibition_ic50_um: z.number().nullable().optional(),
  cyp_inhibition_profile: z.string(),
  off_target_risk_summary: z.string(),
});
export type OffTargetToxicityEvaluation = z.infer<typeof OffTargetToxicityEvaluationSchema>;

export const AnimalToxicityEvaluationSchema = z.object({
  species_evaluated: z.array(z.string()).default([]),
  noael_dose: z.string().nullable().optional(),
  target_organs_in_animals: z.array(z.string()).default([]),
  glp_toxicology_completed: z.boolean(),
  animal_to_human_translation_note: z.string(),
});
export type AnimalToxicityEvaluation = z.infer<typeof AnimalToxicityEvaluationSchema>;

export const TherapeuticWindowEvaluationSchema = z.object({
  therapeutic_window_ratio: z.number(),
  window_width: z.string(),
  safety_margin_description: z.string(),
});
export type TherapeuticWindowEvaluation = z.infer<typeof TherapeuticWindowEvaluationSchema>;

export const DoseExposureRelationshipEvaluationSchema = z.object({
  exposure_safety_correlation: z.string(),
  concentration_dependent_dlt: z.boolean(),
  pk_variability_impact: z.string(),
});
export type DoseExposureRelationshipEvaluation = z.infer<typeof DoseExposureRelationshipEvaluationSchema>;

export const MajorRiskSignalSchema = z.object({
  signal_id: z.string(),
  title: z.string(),
  severity: RiskSignalSeveritySchema,
  affected_organ: OrganSystemSchema,
  clinical_evidence: z.string(),
  management_recommendation: z.string(),
});
export type MajorRiskSignal = z.infer<typeof MajorRiskSignalSchema>;

export const SafetyIntelligenceProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  safety_rating: SafetyRatingSchema,
  safety_score: z.number().min(0).max(100),
  therapeutic_index_score: z.number().min(0).max(100),
  safety_confidence: z.number().min(0).max(1),
  major_risk_signals: z.array(MajorRiskSignalSchema).default([]),
  common_adverse_events: z.array(AdverseEventRecordSchema).default([]),
  grade_3_plus_adverse_events: z.array(AdverseEventRecordSchema).default([]),
  dose_limiting_toxicity: DoseLimitingToxicityEvaluationSchema,
  discontinuation: DiscontinuationEvaluationSchema,
  organ_toxicities: z.array(OrganToxicityProfileSchema).default([]),
  target_related_toxicity: TargetRelatedToxicityEvaluationSchema,
  off_target_toxicity: OffTargetToxicityEvaluationSchema,
  animal_toxicity: AnimalToxicityEvaluationSchema,
  therapeutic_window: TherapeuticWindowEvaluationSchema,
  dose_exposure_relationship: DoseExposureRelationshipEvaluationSchema,
  has_missing_evidence: z.boolean().default(false),
  missing_evidence_details: z.array(z.string()).default([]),
  evidence_citations: z.array(z.record(z.string(), z.any())).default([]),
  disclaimer: z.string(),
  evaluated_at: z.string().datetime().or(z.date()),
});
export type SafetyIntelligenceProfile = z.infer<typeof SafetyIntelligenceProfileSchema>;

export const EvaluateSafetyRequestSchema = z.object({
  asset_id: z.string(),
  target_indication: z.string().optional(),
  min_confidence: z.number().min(0).max(1).default(0.0),
});
export type EvaluateSafetyRequest = z.infer<typeof EvaluateSafetyRequestSchema>;
