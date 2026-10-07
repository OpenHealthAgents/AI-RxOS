import { z } from "zod";

export const KGNodeTypeSchema = z.enum([
  "ASSET",
  "TARGET",
  "GENE",
  "MUTATION",
  "PATHWAY",
  "DISEASE",
  "INDICATION",
  "BIOMARKER",
  "PATIENT_POPULATION",
  "TRIAL",
  "PUBLICATION",
  "COMPANY",
  "INSTITUTION",
  "COMPETITOR",
  "RESISTANCE_MECHANISM",
  "COMBINATION",
  "PATENT",
  "LICENSE",
  "REGULATORY_EVENT",
]);
export type KGNodeType = z.infer<typeof KGNodeTypeSchema>;

export const KGRelationshipTypeSchema = z.enum([
  "TARGETS",
  "INVOLVES_GENE",
  "HARBORS_MUTATION",
  "MODULATES_PATHWAY",
  "TREATS_DISEASE",
  "INDICATED_FOR",
  "STRATIFIED_BY_BIOMARKER",
  "ENROLLS_POPULATION",
  "EVALUATED_IN_TRIAL",
  "REPORTED_IN_PUB",
  "DEVELOPED_BY_COMPANY",
  "ORIGINATED_AT_INSTITUTION",
  "COMPETES_WITH",
  "ACQUIRES_RESISTANCE",
  "OVERCOMES_RESISTANCE_VIA",
  "COVERED_BY_PATENT",
  "SUBJECT_TO_LICENSE",
  "GOVERNED_BY_REGULATORY_EVENT",
]);
export type KGRelationshipType = z.infer<typeof KGRelationshipTypeSchema>;

export const EdgeEvidenceProvenanceSchema = z.object({
  evidence_id: z.string().uuid(),
  evidence_type: z.string().default("LITERATURE"),
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  source_document_id: z.string().nullable().optional(),
  polarity: z.string().default("SUPPORTING"),
  confidence: z.number().min(0).max(1).default(1.0),
  created_at: z.string().datetime().optional(),
});
export type EdgeEvidenceProvenance = z.infer<typeof EdgeEvidenceProvenanceSchema>;

export const KGNodeSchema = z.object({
  id: z.string().uuid(),
  node_type: KGNodeTypeSchema,
  external_id: z.string(),
  name: z.string(),
  display_label: z.string(),
  properties: z.record(z.string(), z.unknown()).default({}),
  created_at: z.string().datetime().optional(),
});
export type KGNode = z.infer<typeof KGNodeSchema>;

export const KGEdgeSchema = z.object({
  id: z.string().uuid(),
  source_node_id: z.string().uuid(),
  relationship_type: KGRelationshipTypeSchema,
  target_node_id: z.string().uuid(),
  confidence: z.number().min(0).max(1).default(1.0),
  properties: z.record(z.string(), z.unknown()).default({}),
  evidence_lineage: z.array(EdgeEvidenceProvenanceSchema).default([]),
  created_at: z.string().datetime().optional(),
});
export type KGEdge = z.infer<typeof KGEdgeSchema>;

export const GraphNodeSummarySchema = z.object({
  node_id: z.string().uuid(),
  node_type: KGNodeTypeSchema,
  name: z.string(),
  display_label: z.string(),
  properties: z.record(z.string(), z.unknown()).default({}),
});
export type GraphNodeSummary = z.infer<typeof GraphNodeSummarySchema>;

export const GraphPathMatchSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  matched_nodes: z.array(GraphNodeSummarySchema).default([]),
  evidence_lineage: z.array(EdgeEvidenceProvenanceSchema).default([]),
  explanation: z.string(),
});
export type GraphPathMatch = z.infer<typeof GraphPathMatchSchema>;

export const OncologyGraphQueryResultSchema = z.object({
  question_id: z.number().int(),
  question_text: z.string(),
  matched_assets_count: z.number().int(),
  matches: z.array(GraphPathMatchSchema).default([]),
  queried_at: z.string().datetime().optional(),
});
export type OncologyGraphQueryResult = z.infer<typeof OncologyGraphQueryResultSchema>;

export const RelationshipProvenanceDetailSchema = z.object({
  edge_id: z.string().uuid(),
  relationship_type: KGRelationshipTypeSchema,
  relationship_category: z.string(),
  source_node: GraphNodeSummarySchema,
  target_node: GraphNodeSummarySchema,
  confidence: z.number().min(0).max(1).default(1.0),
  properties: z.record(z.string(), z.unknown()).default({}),
  evidence_lineage: z.array(EdgeEvidenceProvenanceSchema).default([]),
});
export type RelationshipProvenanceDetail = z.infer<typeof RelationshipProvenanceDetailSchema>;

export const AssetOpportunityGraphSchema = z.object({
  asset_id: z.string().uuid(),
  asset_name: z.string(),
  total_relationships: z.number().int(),
  relationships_by_category: z.record(z.string(), z.array(RelationshipProvenanceDetailSchema)).default({}),
  covered_categories: z.array(z.string()).default([]),
  all_relationships_have_provenance: z.boolean().default(true),
  generated_at: z.string().datetime().optional(),
});
export type AssetOpportunityGraph = z.infer<typeof AssetOpportunityGraphSchema>;

