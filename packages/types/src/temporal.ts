import { z } from "zod";
import {
  DevelopmentStageSchema,
  StageTransitionProbabilitiesSchema,
  StrategicActionSchema,
} from "./opportunity";

export const OutcomeTypeSchema = z.enum([
  "trial_readout",
  "trial_failure",
  "regulatory_approval",
  "complete_response_letter",
  "advisory_committee_vote",
  "company_acquisition",
  "licensing_deal",
  "biomarker_discovery",
  "clinical_hold",
  "black_box_warning",
]);
export type OutcomeType = z.infer<typeof OutcomeTypeSchema>;

export const LeakageViolationTypeSchema = z.enum([
  "future_publication",
  "future_trial_result",
  "future_regulatory_decision",
  "future_outcome_disclosure",
  "future_acquisition",
  "future_licensing_deal",
  "future_biomarker_discovery",
  "future_observation_date",
]);
export type LeakageViolationType = z.infer<typeof LeakageViolationTypeSchema>;

export const TemporalCoordinatesSchema = z.object({
  evidence_publication_date: z.string().nullable().optional(),
  evidence_observation_date: z.string().nullable().optional(),
  trial_date: z.string().nullable().optional(),
  outcome_date: z.string().nullable().optional(),
  regulatory_date: z.string().nullable().optional(),
  prediction_cutoff_date: z.string(),
  publicly_known_date: z.string().nullable().optional(),
});
export type TemporalCoordinates = z.infer<typeof TemporalCoordinatesSchema>;

export const EvidenceCutoffSchema = z.object({
  cutoff_date: z.string(),
  enforce_strict_publication_boundary: z.boolean().default(true),
  enforce_strict_public_disclosure_boundary: z.boolean().default(true),
  description: z.string().nullable().optional(),
});
export type EvidenceCutoff = z.infer<typeof EvidenceCutoffSchema>;

export const OutcomeAvailabilitySchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  outcome_type: OutcomeTypeSchema,
  headline: z.string(),
  description: z.string(),
  event_date: z.string(),
  publicly_known_date: z.string(),
  disclosure_source: z.string(),
  disclosure_url: z.string().nullable().optional(),
  is_favorable: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type OutcomeAvailability = z.infer<typeof OutcomeAvailabilitySchema>;

export const LeakageViolationSchema = z.object({
  violation_type: LeakageViolationTypeSchema,
  entity_id: z.string(),
  entity_name: z.string(),
  entity_date: z.string(),
  cutoff_date: z.string(),
  days_post_cutoff: z.number().int(),
  details: z.string(),
});
export type LeakageViolation = z.infer<typeof LeakageViolationSchema>;

export const LeakageAuditReportSchema = z.object({
  asset_id: z.string().uuid(),
  cutoff_date: z.string(),
  audit_passed: z.boolean(),
  total_eligible_items: z.number().int(),
  total_suppressed_items: z.number().int(),
  violations: z.array(LeakageViolationSchema).default([]),
  audit_hash: z.string(),
  audit_timestamp: z.string().datetime().optional(),
});
export type LeakageAuditReport = z.infer<typeof LeakageAuditReportSchema>;

export const PredictionSnapshotSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  cutoff_date: z.string(),
  model_name: z.string().default("CalibratedBayesianOpportunityEngine"),
  model_version: z.string().default("v0.1-historical"),
  input_feature_hash: z.string(),
  predicted_action: StrategicActionSchema,
  predicted_dps: z.number().min(0).max(100),
  predicted_transitions: StageTransitionProbabilitiesSchema,
  confidence: z.number().min(0).max(1.0),
  rationale: z.string(),
  eligible_evidence_count: z.number().int(),
  suppressed_future_evidence_count: z.number().int(),
  anti_leakage_audit_passed: z.boolean().default(true),
  created_at: z.string().datetime().optional(),
});
export type PredictionSnapshot = z.infer<typeof PredictionSnapshotSchema>;

export const HistoricalSnapshotSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  cutoff: EvidenceCutoffSchema,
  stage_at_cutoff: DevelopmentStageSchema,
  owner_at_cutoff: z.string(),
  indication_at_cutoff: z.string(),
  prediction: PredictionSnapshotSchema,
  known_outcomes_at_cutoff: z.array(OutcomeAvailabilitySchema).default([]),
  suppressed_future_outcomes: z.array(OutcomeAvailabilitySchema).default([]),
  ground_truth_post_cutoff_outcome: z.string().nullable().optional(),
  accuracy_assessment: z.string().nullable().optional(),
  audit_report: LeakageAuditReportSchema,
  created_at: z.string().datetime().optional(),
});
export type HistoricalSnapshot = z.infer<typeof HistoricalSnapshotSchema>;
