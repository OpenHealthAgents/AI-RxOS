import { z } from "zod";

/**
 * 8 Search Target Entities
 */
export const SearchTargetTypeSchema = z.enum([
  "asset",
  "target",
  "indication",
  "biomarker",
  "trial",
  "publication",
  "company",
  "opportunity",
]);
export type SearchTargetType = z.infer<typeof SearchTargetTypeSchema>;

export const SearchModeSchema = z.enum(["structured", "semantic", "hybrid"]);
export type SearchMode = z.infer<typeof SearchModeSchema>;

export const OperatorTypeSchema = z.enum([
  "eq",
  "neq",
  "contains",
  "in",
  "gt",
  "gte",
  "lt",
  "lte",
  "between",
  "is",
]);
export type OperatorType = z.infer<typeof OperatorTypeSchema>;

/**
 * Structured Constraint parsed from natural language.
 */
export const StructuredConstraintSchema = z.object({
  field: z.string(),
  operator: OperatorTypeSchema,
  value: z.union([
    z.string(),
    z.number(),
    z.boolean(),
    z.array(z.string()),
    z.array(z.number()),
  ]),
  confidence: z.number().min(0).max(1).default(1.0),
  source_span: z.string().nullable().optional(),
});
export type StructuredConstraint = z.infer<typeof StructuredConstraintSchema>;

/**
 * Validated Intermediate Representation of parsed natural language query.
 */
export const ParsedSearchQuerySchema = z.object({
  raw_query: z.string(),
  target_type: SearchTargetTypeSchema,
  search_mode: SearchModeSchema.default("hybrid"),
  semantic_intent: z.string().default(""),
  structured_constraints: z.array(StructuredConstraintSchema).default([]),
  extracted_entities: z.record(z.string(), z.array(z.string())).default({}),
  is_validated: z.boolean().default(false),
  validation_errors: z.array(z.string()).default([]),
});
export type ParsedSearchQuery = z.infer<typeof ParsedSearchQuerySchema>;

/**
 * Validated Parametric SQL Query AST.
 */
export const ValidatedParametricQuerySchema = z.object({
  target_table: z.string(),
  sql_template: z.string(),
  parameters: z.record(z.string(), z.unknown()),
  active_filters: z.array(z.string()),
  audit_trace: z.string(),
});
export type ValidatedParametricQuery = z.infer<typeof ValidatedParametricQuerySchema>;

/**
 * User-facing Search Request.
 */
export const SearchQueryRequestSchema = z.object({
  query: z.string().min(1),
  target_type: SearchTargetTypeSchema.default("asset"),
  mode: SearchModeSchema.default("hybrid"),
  explicit_constraints: z.array(StructuredConstraintSchema).nullable().optional(),
  limit: z.number().int().min(1).max(100).default(10),
  offset: z.number().int().min(0).default(0),
});
export type SearchQueryRequest = z.infer<typeof SearchQueryRequestSchema>;

export const SearchEvidenceProvenanceSchema = z.object({
  evidence_id: z.string(),
  evidence_type: z.string(),
  source_citation: z.string(),
  source_url: z.string().nullable().optional(),
  confidence: z.number().min(0).max(1).default(1.0),
});
export type SearchEvidenceProvenance = z.infer<typeof SearchEvidenceProvenanceSchema>;

export const SearchResultItemSchema = z.object({
  id: z.string(),
  entity_type: SearchTargetTypeSchema,
  title: z.string(),
  subtitle: z.string().nullable().optional(),
  score: z.number().min(0).max(100),
  semantic_similarity: z.number().nullable().optional(),
  structured_match: z.boolean().default(true),
  match_reasons: z.array(z.string()).default([]),
  attributes: z.record(z.string(), z.unknown()).default({}),
  evidence: z.array(SearchEvidenceProvenanceSchema).default([]),
  unknowns: z.array(z.string()).default([]),
});
export type SearchResultItem = z.infer<typeof SearchResultItemSchema>;

export const SearchExecutionResultSchema = z.object({
  query_id: z.string().uuid(),
  raw_query: z.string(),
  target_type: SearchTargetTypeSchema,
  search_mode: SearchModeSchema,
  parsed_query: ParsedSearchQuerySchema,
  validated_sql: ValidatedParametricQuerySchema.nullable().optional(),
  total_matches: z.number().int().nonnegative(),
  returned_count: z.number().int().nonnegative(),
  items: z.array(SearchResultItemSchema),
  execution_time_ms: z.number(),
  timestamp: z.string().datetime(),
});
export type SearchExecutionResult = z.infer<typeof SearchExecutionResultSchema>;
