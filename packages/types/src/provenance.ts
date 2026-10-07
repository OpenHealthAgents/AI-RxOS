import { z } from "zod";
import { StrategicActionSchema, StrategicAction } from "./opportunity";
import {
  SourceTypeSchema,
  SourceType,
  EvidenceSourceSchema,
  EvidenceSource,
  EvidenceExtractionSchema,
  EvidenceExtraction,
  EvidenceObservationRichSchema,
  EvidenceObservationRich,
  DerivedFeatureSchema,
  DerivedFeature,
  ModelOutputSchema,
  ModelOutput,
  RecommendationLineageSchema,
  RecommendationLineage,
} from "./evidence";

// ==============================================================================
// 1. Provenance Stages & Node Types
// ==============================================================================

export const ProvenanceStageSchema = z.enum([
  "source",
  "extraction",
  "normalization",
  "feature_derivation",
  "model_input",
  "model_output",
  "decision_input",
]);
export type ProvenanceStage = z.infer<typeof ProvenanceStageSchema>;

export const ProvenanceNodeTypeSchema = z.enum([
  "source",
  "extraction",
  "normalization",
  "feature_derivation",
  "model_input",
  "model_output",
  "decision_input",
  "recommendation",
]);
export type ProvenanceNodeType = z.infer<typeof ProvenanceNodeTypeSchema>;

export const ProvenanceEdgeTypeSchema = z.enum([
  "extracted_from",
  "normalized_from",
  "derived_from",
  "fed_into_model",
  "predicted_by",
  "decided_from",
  "supports",
  "contradicts",
]);
export type ProvenanceEdgeType = z.infer<typeof ProvenanceEdgeTypeSchema>;

// ==============================================================================
// 2. Canonical Immutable Provenance Node
// ==============================================================================

export const ProvenanceNodeSchema = z.object({
  id: z.string().uuid(),
  asset_id: z.string().uuid(),
  stage: ProvenanceStageSchema,
  node_type: ProvenanceNodeTypeSchema,
  entity_id: z.string().uuid(),
  label: z.string(),
  description: z.string().default(""),
  payload_summary: z.record(z.string(), z.unknown()).default({}),
  content_hash: z.string().length(64), // SHA-256
  parent_hashes: z.array(z.string().length(64)).default([]),
  parent_node_ids: z.array(z.string().uuid()).default([]),
  timestamp: z.string().datetime(),
  metadata: z.record(z.string(), z.unknown()).default({}),
});
export type ProvenanceNode = z.infer<typeof ProvenanceNodeSchema>;

// ==============================================================================
// 3. Provenance Edge
// ==============================================================================

export const ProvenanceEdgeSchema = z.object({
  id: z.string().uuid(),
  source_node_id: z.string().uuid(),
  target_node_id: z.string().uuid(),
  source_stage: ProvenanceStageSchema,
  target_stage: ProvenanceStageSchema,
  edge_type: ProvenanceEdgeTypeSchema,
  weight: z.number().min(0).max(1.0).default(1.0),
  hash_signature: z.string().length(64), // SHA-256
  created_at: z.string().datetime().optional(),
});
export type ProvenanceEdge = z.infer<typeof ProvenanceEdgeSchema>;

// ==============================================================================
// 4. Stage-Specific Payloads
// ==============================================================================

export const NormalizationRecordSchema = z.object({
  id: z.string().uuid(),
  extraction_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  raw_value: z.string(),
  normalized_value: z.number(),
  normalized_unit: z.string(),
  parameter_name: z.string(),
  normalizer_version: z.string().default("v1.0"),
  transformation_rule: z.string(),
  confidence: z.number().min(0).max(1.0).default(0.95),
  content_hash: z.string().length(64),
  created_at: z.string().datetime().optional(),
});
export type NormalizationRecord = z.infer<typeof NormalizationRecordSchema>;

export const ModelInputRecordSchema = z.object({
  id: z.string().uuid(),
  model_name: z.string(),
  model_version: z.string().default("v0.1"),
  asset_id: z.string().uuid(),
  feature_ids: z.array(z.string().uuid()),
  feature_vector: z.record(z.string(), z.number()),
  input_schema_version: z.string().default("v1.0"),
  content_hash: z.string().length(64),
  created_at: z.string().datetime().optional(),
});
export type ModelInputRecord = z.infer<typeof ModelInputRecordSchema>;

export const DecisionInputRecordSchema = z.object({
  id: z.string().uuid(),
  recommendation_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  action: StrategicActionSchema,
  model_output_ids: z.array(z.string().uuid()),
  model_scores: z.record(z.string(), z.number()),
  decision_policy_version: z.string().default("v1.0"),
  thresholds_applied: z.record(z.string(), z.number()).default({}),
  content_hash: z.string().length(64),
  created_at: z.string().datetime().optional(),
});
export type DecisionInputRecord = z.infer<typeof DecisionInputRecordSchema>;

// ==============================================================================
// 5. Complete Provenance Graph (DAG)
// ==============================================================================

export const ProvenanceGraphSchema = z.object({
  recommendation_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  root_source_ids: z.array(z.string().uuid()).default([]),
  nodes: z.array(ProvenanceNodeSchema).default([]),
  edges: z.array(ProvenanceEdgeSchema).default([]),
  stage_counts: z.record(ProvenanceStageSchema, z.number()).default({
    source: 0,
    extraction: 0,
    normalization: 0,
    feature_derivation: 0,
    model_input: 0,
    model_output: 0,
    decision_input: 0,
  }),
  root_to_leaf_paths: z.array(z.array(z.string().uuid())).default([]),
  is_dag_valid: z.boolean().default(true),
  is_immutable_verified: z.boolean().default(true),
  merkle_root_hash: z.string().length(64),
  created_at: z.string().datetime().optional(),
});
export type ProvenanceGraph = z.infer<typeof ProvenanceGraphSchema>;

// ==============================================================================
// 6. Provenance Traceback Query Result
// ==============================================================================

export const TracebackStepSchema = z.object({
  stage: ProvenanceStageSchema,
  node_id: z.string().uuid(),
  entity_id: z.string().uuid(),
  label: z.string(),
  content_hash: z.string().length(64),
  summary: z.record(z.string(), z.unknown()),
  parent_node_ids: z.array(z.string().uuid()).default([]),
});
export type TracebackStep = z.infer<typeof TracebackStepSchema>;

export const ProvenanceTracebackResultSchema = z.object({
  recommendation_id: z.string().uuid(),
  asset_id: z.string().uuid(),
  action: StrategicActionSchema,
  merkle_root_hash: z.string().length(64),
  unbroken_chain: z.boolean().default(true),
  chain_length: z.number().int().default(7),
  terminal_decision: TracebackStepSchema,
  model_output_step: TracebackStepSchema,
  model_input_step: TracebackStepSchema,
  feature_derivation_steps: z.array(TracebackStepSchema).default([]),
  normalization_steps: z.array(TracebackStepSchema).default([]),
  extraction_steps: z.array(TracebackStepSchema).default([]),
  underlying_sources: z.array(EvidenceSourceSchema).default([]),
  audit_hash_verified: z.boolean().default(true),
});
export type ProvenanceTracebackResult = z.infer<typeof ProvenanceTracebackResultSchema>;
