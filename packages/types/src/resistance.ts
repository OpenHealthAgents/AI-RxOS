import { z } from "zod";

export const ResistanceCategorySchema = z.enum([
  "target mutation",
  "target amplification",
  "bypass signaling",
  "downstream activation",
  "pathway adaptation",
  "phenotypic escape",
  "tumor microenvironment mechanisms",
  "metabolic adaptation",
]);
export type ResistanceCategory = z.infer<typeof ResistanceCategorySchema>;

export const ResistanceClassificationSchema = z.enum([
  "Clinically observed",
  "Observed",
  "Preclinical",
  "Mechanistically inferred",
  "AI-predicted",
]);
export type ResistanceClassification = z.infer<typeof ResistanceClassificationSchema>;

export const ResistanceRiskTierSchema = z.enum([
  "VERY_HIGH",
  "HIGH",
  "MODERATE",
  "LOW",
]);
export type ResistanceRiskTier = z.infer<typeof ResistanceRiskTierSchema>;

export const ImpactSeveritySchema = z.enum([
  "CRITICAL",
  "HIGH",
  "MODERATE",
  "LOW",
]);
export type ImpactSeverity = z.infer<typeof ImpactSeveritySchema>;

export const PotentialInterventionSchema = z.object({
  strategy_type: z.string(),
  intervention_name: z.string(),
  target_mechanism: z.string(),
  mechanistic_rationale: z.string(),
  development_status: z.string(),
  feasibility_score: z.number().min(0).max(1),
  citations: z.array(z.string()).default([]),
});
export type PotentialIntervention = z.infer<typeof PotentialInterventionSchema>;

export const EscapeMechanismSchema = z.object({
  id: z.string(),
  mechanism_name: z.string(),
  category: ResistanceCategorySchema,
  classification: ResistanceClassificationSchema,
  is_known_mechanism: z.boolean().default(true),
  is_experimentally_proven: z.boolean().default(false),
  frequency_pct: z.number().nullable().optional(),
  impact_severity: ImpactSeveritySchema,
  molecular_description: z.string(),
  potential_intervention: PotentialInterventionSchema,
  evidence_citations: z.array(z.record(z.string(), z.any())).default([]),
  confidence: z.number().min(0).max(1),
  epistemic_status_note: z.string(),
});
export type EscapeMechanism = z.infer<typeof EscapeMechanismSchema>;

export const ResistanceRiskProfileSchema = z.object({
  asset_id: z.string(),
  asset_name: z.string(),
  overall_risk_score: z.number().min(0).max(100),
  risk_tier: ResistanceRiskTierSchema,
  primary_vulnerability: z.string(),
  top_escape_mechanisms: z.array(EscapeMechanismSchema),
  mechanisms_by_category: z.record(z.string(), z.array(EscapeMechanismSchema)).default({}),
  evidence_summary: z.string(),
  overall_confidence: z.number().min(0).max(1),
  recommended_interventions: z.array(PotentialInterventionSchema).default([]),
  epistemic_audit: z.record(z.string(), z.any()).default({}),
  disclaimer: z.string(),
  evaluated_at: z.string().datetime().or(z.date()),
});
export type ResistanceRiskProfile = z.infer<typeof ResistanceRiskProfileSchema>;

export const EvaluateResistanceRequestSchema = z.object({
  asset_id: z.string(),
  include_ai_predicted: z.boolean().default(true),
  min_confidence: z.number().min(0).max(1).default(0.0),
});
export type EvaluateResistanceRequest = z.infer<typeof EvaluateResistanceRequestSchema>;

export const ResistanceInterventionComparisonSchema = z.object({
  asset_id: z.string(),
  escape_mechanism_id: z.string(),
  escape_mechanism_name: z.string(),
  category: ResistanceCategorySchema,
  interventions: z.array(PotentialInterventionSchema),
  preferred_intervention: PotentialInterventionSchema,
});
export type ResistanceInterventionComparison = z.infer<typeof ResistanceInterventionComparisonSchema>;
