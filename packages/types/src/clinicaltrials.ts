import { z } from "zod";

export const NormalizedClinicalStageSchema = z.enum([
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
export type NormalizedClinicalStage = z.infer<typeof NormalizedClinicalStageSchema>;

export const InterventionItemSchema = z.object({
  intervention_type: z.string().default("DRUG"),
  name: z.string(),
  description: z.string().nullable().optional(),
});
export type InterventionItem = z.infer<typeof InterventionItemSchema>;

export const ArmItemSchema = z.object({
  arm_label: z.string(),
  arm_type: z.string().default("EXPERIMENTAL"),
  intervention_names: z.array(z.string()).default([]),
});
export type ArmItem = z.infer<typeof ArmItemSchema>;

export const EndpointItemSchema = z.object({
  endpoint_title: z.string(),
  endpoint_type: z.string().default("PRIMARY"),
  time_frame: z.string().nullable().optional(),
  description: z.string().nullable().optional(),
});
export type EndpointItem = z.infer<typeof EndpointItemSchema>;

export const TrialOutcomeItemSchema = z.object({
  endpoint_name: z.string(),
  metric: z.string(),
  value: z.number().nullable().optional(),
  unit: z.string().nullable().optional(),
  confidence_interval: z.string().nullable().optional(),
});
export type TrialOutcomeItem = z.infer<typeof TrialOutcomeItemSchema>;

export const AdverseEventItemSchema = z.object({
  term: z.string(),
  grade: z.string().nullable().default("Grade 3+"),
  affected_count: z.number().int().nullable().optional(),
  total_evaluated: z.number().int().nullable().optional(),
  frequency_pct: z.number().nullable().optional(),
  is_serious: z.boolean().default(false),
});
export type AdverseEventItem = z.infer<typeof AdverseEventItemSchema>;

export const TrialStatusHistorySchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  as_of_date: z.string(),
  overall_status: z.string(),
  normalized_stage: NormalizedClinicalStageSchema,
  why_stopped: z.string().nullable().optional(),
  enrollment: z.number().int().nullable().optional(),
  results_posted: z.boolean().default(false),
  change_summary: z.string().default(""),
  created_at: z.string().datetime().optional(),
});
export type TrialStatusHistory = z.infer<typeof TrialStatusHistorySchema>;

export const ClinicalTrialRecordSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  study_title: z.string(),
  official_title: z.string().nullable().optional(),
  sponsor: z.string(),
  collaborators: z.array(z.string()).default([]),
  phase_raw: z.string(),
  normalized_stage: NormalizedClinicalStageSchema,
  status: z.string(),
  enrollment: z.number().int().nullable().optional(),
  interventions: z.array(InterventionItemSchema).default([]),
  arms: z.array(ArmItemSchema).default([]),
  conditions: z.array(z.string()).default([]),
  biomarkers: z.array(z.string()).default([]),
  population: z.string().default(""),
  eligibility: z.record(z.string(), z.unknown()).default({}),
  endpoints: z.array(EndpointItemSchema).default([]),
  outcomes: z.array(TrialOutcomeItemSchema).default([]),
  results: z.record(z.string(), z.unknown()).nullable().optional(),
  adverse_events: z.array(AdverseEventItemSchema).default([]),
  termination_reason: z.string().nullable().optional(),
  withdrawal_reason: z.string().nullable().optional(),
  publication_links: z.array(z.string()).default([]),
  start_date: z.string().nullable().optional(),
  primary_completion_date: z.string().nullable().optional(),
  results_first_posted_date: z.string().nullable().optional(),
  status_history: z.array(TrialStatusHistorySchema).default([]),
  content_hash: z.string().default(""),
  created_at: z.string().datetime().optional(),
});
export type ClinicalTrialRecord = z.infer<typeof ClinicalTrialRecordSchema>;

export const TrialAssetMappingSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  asset_id: z.string().uuid(),
  canonical_name: z.string(),
  intervention_name: z.string(),
  is_primary: z.boolean().default(true),
  confidence: z.number().default(1.0),
});
export type TrialAssetMapping = z.infer<typeof TrialAssetMappingSchema>;

export const TrialIndicationMappingSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  indication_id: z.string().uuid().nullable().optional(),
  condition_name: z.string(),
  cancer_subtype: z.string().nullable().optional(),
  confidence: z.number().default(0.95),
});
export type TrialIndicationMapping = z.infer<typeof TrialIndicationMappingSchema>;

export const TrialBiomarkerMappingSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  biomarker_id: z.string().uuid().nullable().optional(),
  biomarker_text: z.string(),
  gene_symbol: z.string().nullable().optional(),
  inclusion_status: z.string().default("REQUIRED"),
});
export type TrialBiomarkerMapping = z.infer<typeof TrialBiomarkerMappingSchema>;

export const TrialCompanyMappingSchema = z.object({
  id: z.string().uuid(),
  nct_id: z.string(),
  company_id: z.string().uuid().nullable().optional(),
  company_name: z.string(),
  role: z.string().default("LEAD_SPONSOR"),
});
export type TrialCompanyMapping = z.infer<typeof TrialCompanyMappingSchema>;

export const TrialResolutionSummarySchema = z.object({
  nct_id: z.string(),
  assets: z.array(TrialAssetMappingSchema).default([]),
  indications: z.array(TrialIndicationMappingSchema).default([]),
  biomarkers: z.array(TrialBiomarkerMappingSchema).default([]),
  companies: z.array(TrialCompanyMappingSchema).default([]),
});
export type TrialResolutionSummary = z.infer<typeof TrialResolutionSummarySchema>;
