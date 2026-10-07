import { z } from "zod";
import { ScientificEvidenceStateSchema } from "./opportunity";

export const ExtractionCategorySchema = z.enum([
  "asset",
  "drug",
  "target",
  "gene",
  "mutation",
  "disease",
  "biomarker",
  "model",
  "cell_line",
  "animal_model",
  "efficacy",
  "toxicity",
  "cns",
  "cns_exposure",
  "cns_efficacy",
  "resistance",
  "combination",
  "clinical_result",
  "clinical_outcome",
]);
export type ExtractionCategory = z.infer<typeof ExtractionCategorySchema>;

export const IngestionStatusSchema = z.enum([
  "INGESTED",
  "DUPLICATE_SKIPPED",
  "RETRIED_AND_SUCCEEDED",
  "FAILED",
]);
export type IngestionStatus = z.infer<typeof IngestionStatusSchema>;

export const ExtractionLineageSchema = z.object({
  lineage_id: z.string().uuid(),
  pmid: z.string(),
  article_title: z.string(),
  journal: z.string(),
  publication_date: z.string(),
  extractor_model: z.string(),
  extraction_timestamp: z.string(),
  source_location: z.string(),
  raw_verbatim_quote: z.string(),
  provenance_hash: z.string(),
  evidence_source_id: z.string().uuid().nullable().optional(),
});
export type ExtractionLineage = z.infer<typeof ExtractionLineageSchema>;

export const QualityCheckRuleSchema = z.object({
  rule_name: z.string(),
  passed: z.boolean(),
  score: z.number().min(0).max(100),
  details: z.string(),
  is_blocking: z.boolean().default(false),
});
export type QualityCheckRule = z.infer<typeof QualityCheckRuleSchema>;

export const PubMedQualityReportSchema = z.object({
  pmid: z.string(),
  overall_quality_score: z.number().min(0).max(100),
  quality_tier: z.enum(["HIGH", "MEDIUM", "LOW", "REJECTED"]),
  quality_passed: z.boolean(),
  hallucination_check_passed: z.boolean(),
  rules: z.array(QualityCheckRuleSchema),
  timestamp: z.string().datetime().optional(),
});
export type PubMedQualityReport = z.infer<typeof PubMedQualityReportSchema>;

export const ExtractedObservationSchema = z.object({
  id: z.string().uuid(),
  pmid: z.string(),
  extraction_category: ExtractionCategorySchema,
  entity_text: z.string(),
  extracted_text: z.string(),
  source_location: z.string(),
  normalized_value: z.number().nullable().optional(),
  normalized_unit: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1.0).default(0.88),
  is_ground_truth: z.boolean().default(false),
  epistemic_status: ScientificEvidenceStateSchema.default("ai_inference"),
  extraction_model_version: z.string().default("BioExtractor-Ensemble-v2.1"),
  resolved_canonical_id: z.string().uuid().nullable().optional(),
  resolved_canonical_name: z.string().nullable().optional(),
  entity_resolution_confidence: z.number().min(0).max(1.0).optional(),
  resolution_method: z.string().optional(),
  source_citation: z.string(),
  lineage: ExtractionLineageSchema.optional(),
  created_at: z.string().datetime().optional(),
});
export type ExtractedObservation = z.infer<typeof ExtractedObservationSchema>;

export const PubMedArticleRecordSchema = z.object({
  id: z.string().uuid(),
  pmid: z.string(),
  doi: z.string().nullable().optional(),
  title: z.string(),
  abstract: z.string(),
  authors: z.array(z.string()).default([]),
  journal: z.string(),
  publication_date: z.string(),
  study_type: z.string().default("literature"),
  keywords: z.array(z.string()).default([]),
  mesh_terms: z.array(z.string()).default([]),
  mesh: z.array(z.string()).default([]),
  entities: z.array(z.string()).default([]),
  references: z.array(z.string()).default([]),
  raw_source: z.record(z.string(), z.unknown()).default({}),
  source_citation: z.string().default(""),
  content_hash: z.string().default(""),
  retrieval_date: z.string().optional(),
  created_at: z.string().datetime().optional(),
});
export type PubMedArticleRecord = z.infer<typeof PubMedArticleRecordSchema>;

export const IngestionResultSchema = z.object({
  pmid: z.string(),
  status: IngestionStatusSchema,
  is_duplicate: z.boolean().default(false),
  retry_count: z.number().int().default(0),
  observations_count: z.number().int().default(0),
  resolved_entities_count: z.number().int().default(0),
  content_hash: z.string(),
  execution_duration_ms: z.number().default(0.0),
  audit_id: z.string().uuid(),
  observations: z.array(ExtractedObservationSchema).default([]),
  quality_report: PubMedQualityReportSchema.optional(),
  error_message: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type IngestionResult = z.infer<typeof IngestionResultSchema>;

export const PubMedBatchIngestRequestSchema = z.object({
  articles: z.array(PubMedArticleRecordSchema),
  force_reprocess: z.boolean().default(false),
  run_quality_checks: z.boolean().default(true),
});
export type PubMedBatchIngestRequest = z.infer<typeof PubMedBatchIngestRequestSchema>;

