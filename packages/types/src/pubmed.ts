import { z } from "zod";
import { ScientificEvidenceStateSchema } from "./opportunity";

export const ExtractionCategorySchema = z.enum([
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
  "cns_exposure",
  "cns_efficacy",
  "resistance",
  "combination",
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
  source_citation: z.string(),
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
  error_message: z.string().nullable().optional(),
  created_at: z.string().datetime().optional(),
});
export type IngestionResult = z.infer<typeof IngestionResultSchema>;
