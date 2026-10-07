import { z } from "zod";
import {
  EvidencePolaritySchema,
  ScientificEvidenceStateSchema,
  StrategicActionSchema,
} from "./opportunity";
import {
  EvidenceTemporalMetadataSchema,
  EvidenceTemporalMetadata,
} from "./temporal";

export const SourceTypeSchema = z.enum([
  "publication",
  "clinical_trial",
  "regulatory_source",
  "patent",
  "company_source",
  "conference_abstract",
  "scientific_database",
  "institutional_source",
]);
export type SourceType = z.infer<typeof SourceTypeSchema>;

export const ProspectiveOrRetrospectiveSchema = z.enum([
  "prospective",
  "retrospective",
  "not_applicable",
]);
export type ProspectiveOrRetrospective = z.infer<typeof ProspectiveOrRetrospectiveSchema>;

export const ExtractionMethodSchema = z.enum([
  "llm_structured_extraction",
  "regex_pipeline",
  "curated_expert",
  "ocr_table_parser",
]);
export type ExtractionMethod = z.infer<typeof ExtractionMethodSchema>;

export const RiskOfBiasSchema = z.enum(["low", "moderate", "high", "unclear"]);
export type RiskOfBias = z.infer<typeof RiskOfBiasSchema>;

export const QualityGradeSchema = z.enum([
  "GRADE_A_HIGH",
  "GRADE_B_MODERATE",
  "GRADE_C_LOW",
  "GRADE_D_VERY_LOW",
]);
export type QualityGrade = z.infer<typeof QualityGradeSchema>;

export const ConfidenceLevelSchema = z.enum([
  "very_high",
  "high",
  "medium",
  "low",
  "insufficient",
]);
export type ConfidenceLevel = z.infer<typeof ConfidenceLevelSchema>;

export const StudyDesignTypeSchema = z.enum([
  "rct_double_blind",
  "rct_open_label",
  "prospective_cohort",
  "phase_1_2_single_arm",
  "retrospective_observational",
  "in_vivo_animal_disease_model",
  "ex_vivo_patient_tissue",
  "in_vitro_cell_line",
  "biochemical_kinase_assay",
  "case_report_series",
  "computational_prediction",
]);
export type StudyDesignType = z.infer<typeof StudyDesignTypeSchema>;

export const ModelRelevanceSchema = z.enum([
  "direct_human_clinical",
  "patient_derived_xenograft",
  "syngeneic_animal_model",
  "isogenic_engineered_line",
  "immortalized_cell_line",
  "recombinant_cell_free_assay",
  "computational_silico",
]);
export type ModelRelevance = z.infer<typeof ModelRelevanceSchema>;

export const DirectnessLevelSchema = z.enum([
  "direct",
  "proximate",
  "surrogate",
  "indirect",
]);
export type DirectnessLevel = z.infer<typeof DirectnessLevelSchema>;

export const ReplicationStatusSchema = z.enum([
  "independently_replicated",
  "internally_replicated",
  "single_study_unreplicated",
  "contradicted",
]);
export type ReplicationStatus = z.infer<typeof ReplicationStatusSchema>;

export const ClaimTypeSchema = z.enum([
  "efficacy",
  "selectivity",
  "safety_tolerability",
  "cns_penetration",
  "resistance_risk",
  "commercial_fto",
]);
export type ClaimType = z.infer<typeof ClaimTypeSchema>;

export const LineageStepSchema = z.enum([
  "source_to_extraction",
  "extraction_to_observation",
  "observation_to_claim",
  "observation_to_feature",
  "feature_to_model_output",
  "model_output_to_recommendation",
]);
export type LineageStep = z.infer<typeof LineageStepSchema>;

export const RelationshipTypeSchema = z.enum([
  "supports",
  "contradicts",
  "derives_into",
  "calibrates",
  "contextualizes",
  "rebuts",
]);
export type RelationshipType = z.infer<typeof RelationshipTypeSchema>;

// ==============================================================================
// 1. Temporal Scope, Quality & Confidence
// ==============================================================================

export const EvidenceTemporalScopeSchema = z.object({
  valid_from: z.string(),
  valid_to: z.string().nullable().optional(),
  as_of_date: z.string(),
  is_current: z.boolean().default(true),
  cutoff_compliant: z.boolean().default(true),
});
export type EvidenceTemporalScope = z.infer<typeof EvidenceTemporalScopeSchema>;

export const EvidenceQualitySchema = z.object({
  quality_score: z.number().min(0).max(100).default(85.0),
  methodological_rigor: z.number().min(0).max(100).default(85.0),
  risk_of_bias: RiskOfBiasSchema.default("low"),
  reproducibility_flag: z.boolean().default(true),
  quality_grade: QualityGradeSchema.default("GRADE_A_HIGH"),
  scoring_breakdown: z.record(z.string(), z.number()).default({}),
  limitations: z.array(z.string()).default([]),
});
export type EvidenceQuality = z.infer<typeof EvidenceQualitySchema>;

export const EvidenceConfidenceSchema = z.object({
  score: z.number().min(0).max(1.0).default(0.90),
  confidence_interval_low: z.number().nullable().optional(),
  confidence_interval_high: z.number().nullable().optional(),
  confidence_level: ConfidenceLevelSchema.default("high"),
  epistemic_uncertainty: z.number().min(0).max(1.0).default(0.10),
  aleatoric_uncertainty: z.number().min(0).max(1.0).default(0.05),
  calibration_notes: z.string().nullable().optional(),
});
export type EvidenceConfidence = z.infer<typeof EvidenceConfidenceSchema>;

export const QualityDimensionScoreSchema = z.object({
  dimension: z.string(),
  weight: z.number(),
  raw_score: z.number().min(0).max(100),
  weighted_score: z.number(),
  notes: z.string(),
});
export type QualityDimensionScore = z.infer<typeof QualityDimensionScoreSchema>;

export const EvidenceQualityAppraisalSchema = z.object({
  overall_quality_score: z.number().min(0).max(100),
  quality_grade: QualityGradeSchema,
  calibrated_confidence: z.number().min(0).max(1.0),
  confidence_level: ConfidenceLevelSchema,
  dimension_scores: z.record(z.string(), QualityDimensionScoreSchema),
  scoring_breakdown: z.record(z.string(), z.number()),
  quality: EvidenceQualitySchema,
  confidence: EvidenceConfidenceSchema,
  limitations: z.array(z.string()).default([]),
  is_high_confidence_claim_allowed: z.boolean().default(true),
  epistemic_warning: z.string().nullable().optional(),
});
export type EvidenceQualityAppraisal = z.infer<typeof EvidenceQualityAppraisalSchema>;

// ==============================================================================
// 2. Citations & Sources
// ==============================================================================

export const EvidenceCitationSchema = z.object({
  id: z.string().uuid(),
  source_id: z.string().uuid(),
  formatted_citation: z.string(),
  short_citation: z.string(),
  doi: z.string().nullable().optional(),
  pmid: z.string().nullable().optional(),
  nct_id: z.string().nullable().optional(),
  patent_number: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  citation_style: z.string().default("vancouver"),
  created_at: z.string().datetime().optional(),
});
export type EvidenceCitation = z.infer<typeof EvidenceCitationSchema>;

export const EvidenceSourceSchema = z.object({
  id: z.string().uuid(),
  source_type: SourceTypeSchema,
  source_id: z.string(),
  title: z.string(),
  authors: z.array(z.string()).default([]),
  organization: z.string(),
  publication_date: z.string(),
  retrieval_date: z.string(),
  url_reference: z.string(),
  study_type: z.string(),
  phase: z.string().nullable().optional(),
  species: z.string().nullable().default("Human"),
  model: z.string().nullable().optional(),
  sample_size: z.number().int().nullable().optional(),
  peer_reviewed: z.boolean().default(true),
  peer_review_status: z.string().nullable().optional(),
  prospective_or_retrospective: ProspectiveOrRetrospectiveSchema.default("not_applicable"),
  quality_score: z.number().min(0).max(100).default(85.0),
  confidence: z.number().min(0).max(1.0).default(0.90),
  temporal_validity: EvidenceTemporalScopeSchema,
  temporal_metadata: EvidenceTemporalMetadataSchema.optional(),
  quality: EvidenceQualitySchema.optional(),
  confidence_details: EvidenceConfidenceSchema.optional(),
  citation: EvidenceCitationSchema.optional(),
  created_at: z.string().datetime().optional(),
});
export type EvidenceSource = z.infer<typeof EvidenceSourceSchema>;

// ==============================================================================
// 3. Extractions & Observations
// ==============================================================================

export const EvidenceExtractionSchema = z.object({
  id: z.string().uuid(),
  source_id: z.string().uuid(),
  source_location: z.string(),
  extracted_text: z.string(),
  extraction_method: ExtractionMethodSchema.default("llm_structured_extraction"),
  extractor_model: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1.0).default(0.90),
  extracted_date: z.string(),
  validation_status: z.string().default("validated"),
  created_at: z.string().datetime().optional(),
});
export type EvidenceExtraction = z.infer<typeof EvidenceExtractionSchema>;

export const EvidenceObservationRichSchema = z.object({
  id: z.string().uuid(),
  evidence_id: z.string().uuid(),
  extraction_id: z.string().uuid().nullable().optional(),
  source_id: z.string().uuid(),
  source_ref: z.string(),
  asset_id: z.string().uuid(),
  entity: z.string(),
  parameter_name: z.string(),
  extracted_text_or_value: z.string(),
  normalized_value: z.number(),
  unit: z.string().nullable().optional(),
  observation_date: z.string(),
  source_location: z.string(),
  extraction_method: ExtractionMethodSchema.default("llm_structured_extraction"),
  confidence: z.number().min(0).max(1.0).default(0.90),
  polarity: EvidencePolaritySchema.default("SUPPORTING"),
  observation_state: ScientificEvidenceStateSchema.default("verified_fact"),
  temporal_metadata: EvidenceTemporalMetadataSchema.optional(),
  created_at: z.string().datetime().optional(),
});
export type EvidenceObservationRich = z.infer<typeof EvidenceObservationRichSchema>;

// ==============================================================================
// 4. Claims & Relationships
// ==============================================================================

export const EvidenceClaimSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  claim_text: z.string(),
  claim_type: ClaimTypeSchema,
  polarity: EvidencePolaritySchema.default("SUPPORTING"),
  epistemic_status: ScientificEvidenceStateSchema.default("verified_fact"),
  supporting_observation_ids: z.array(z.string().uuid()).default([]),
  contradicting_observation_ids: z.array(z.string().uuid()).default([]),
  synthesis_confidence: z.number().min(0).max(1.0).default(0.90),
  created_at: z.string().datetime().optional(),
});
export type EvidenceClaim = z.infer<typeof EvidenceClaimSchema>;

export const EvidenceRelationshipSchema = z.object({
  id: z.string().uuid(),
  source_entity_id: z.string().uuid(),
  source_entity_type: z.string(),
  target_entity_id: z.string().uuid(),
  target_entity_type: z.string(),
  relationship_type: RelationshipTypeSchema,
  lineage_step: LineageStepSchema,
  weight: z.number().min(0).max(1.0).default(1.0),
  created_at: z.string().datetime().optional(),
});
export type EvidenceRelationship = z.infer<typeof EvidenceRelationshipSchema>;

// ==============================================================================
// 5. Derived Features & Model Outputs (Lineage Chain)
// ==============================================================================

export const DerivedFeatureSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  feature_name: z.string(),
  computed_value: z.number(),
  calculation_formula: z.string(),
  formula_version: z.string().default("v1.0"),
  confidence: z.number().min(0).max(1.0).default(0.90),
  source_observation_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type DerivedFeature = z.infer<typeof DerivedFeatureSchema>;

export const ModelOutputSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  model_name: z.string(),
  model_version: z.string().default("v0.1"),
  output_metric: z.string(),
  output_value: z.number(),
  confidence: z.number().min(0).max(1.0).default(0.90),
  derived_feature_ids: z.array(z.string().uuid()).default([]),
  created_at: z.string().datetime().optional(),
});
export type ModelOutput = z.infer<typeof ModelOutputSchema>;

export const RecommendationLineageSchema = z.object({
  id: z.string().uuid(),
  recommendation_id: z.string().uuid(),
  model_output_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  action: StrategicActionSchema,
  lineage_hash: z.string(),
  created_at: z.string().datetime().optional(),
});
export type RecommendationLineage = z.infer<typeof RecommendationLineageSchema>;

// ==============================================================================
// 6. Aggregate Evidence & Lineage Graph
// ==============================================================================

export const EvidenceRecordSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  source_type: SourceTypeSchema,
  source_id: z.string(),
  title: z.string(),
  authors: z.array(z.string()).default([]),
  organization: z.string(),
  publication_date: z.string(),
  retrieval_date: z.string(),
  url_reference: z.string(),
  study_type: z.string(),
  phase: z.string().nullable().optional(),
  species: z.string().nullable().default("Human"),
  model: z.string().nullable().optional(),
  sample_size: z.number().int().nullable().optional(),
  peer_reviewed: z.boolean().default(true),
  peer_review_status: z.string().nullable().optional(),
  prospective_or_retrospective: ProspectiveOrRetrospectiveSchema.default("not_applicable"),
  quality_score: z.number().min(0).max(100).default(85.0),
  confidence: z.number().min(0).max(1.0).default(0.90),
  temporal_validity: EvidenceTemporalScopeSchema,
  temporal_metadata: EvidenceTemporalMetadataSchema.optional(),
  quality: EvidenceQualitySchema,
  confidence_details: EvidenceConfidenceSchema,
  citation: EvidenceCitationSchema,
  extractions: z.array(EvidenceExtractionSchema).default([]),
  observations: z.array(EvidenceObservationRichSchema).default([]),
  created_at: z.string().datetime().optional(),
});
export type EvidenceRecord = z.infer<typeof EvidenceRecordSchema>;

export const EvidenceLineageGraphSchema = z.object({
  recommendation_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  sources: z.array(EvidenceSourceSchema).default([]),
  extractions: z.array(EvidenceExtractionSchema).default([]),
  observations: z.array(EvidenceObservationRichSchema).default([]),
  derived_features: z.array(DerivedFeatureSchema).default([]),
  model_outputs: z.array(ModelOutputSchema).default([]),
  relationships: z.array(EvidenceRelationshipSchema).default([]),
  is_lineage_complete: z.boolean().default(true),
  orphaned_components: z.array(z.string()).default([]),
});
export type EvidenceLineageGraph = z.infer<typeof EvidenceLineageGraphSchema>;

// ==============================================================================
// 7. Evidence Ranking Schemas (9 Dimensions)
// ==============================================================================

export const EvidenceRankingTierSchema = z.enum([
  "TIER_1_PINNACLE",
  "TIER_2_HIGH",
  "TIER_3_MODERATE",
  "TIER_4_LOW",
  "TIER_5_INSUFFICIENT",
]);
export type EvidenceRankingTier = z.infer<typeof EvidenceRankingTierSchema>;

export const RankingDimensionDetailSchema = z.object({
  dimension: z.string(),
  weight: z.number(),
  raw_score: z.number().min(0).max(100),
  weighted_score: z.number(),
  justification: z.string(),
});
export type RankingDimensionDetail = z.infer<typeof RankingDimensionDetailSchema>;

export const EvidenceRankingRecordSchema = z.object({
  ranking: z.number().int().positive(),
  evidence_id: z.string(),
  title: z.string(),
  source_citation: z.string(),
  source_type: z.string(),
  publication_date: z.string().nullable().optional(),
  composite_rank_score: z.number().min(0).max(100),
  ranking_tier: EvidenceRankingTierSchema,
  calibrated_confidence: z.number().min(0).max(1),
  is_temporally_valid: z.boolean().default(true),
  dimension_scores: z.record(z.string(), RankingDimensionDetailSchema).default({}),
  ranking_rationale: z.string(),
  key_strengths: z.array(z.string()).default([]),
  limitations: z.array(z.string()).default([]),
});
export type EvidenceRankingRecord = z.infer<typeof EvidenceRankingRecordSchema>;

export const EvidenceRankingResultSchema = z.object({
  query_context: z.string().nullable().optional(),
  as_of_date: z.string(),
  total_candidates: z.number().int().nonnegative(),
  ranked_evidence: z.array(EvidenceRankingRecordSchema),
  ranking_summary: z.string(),
});
export type EvidenceRankingResult = z.infer<typeof EvidenceRankingResultSchema>;

