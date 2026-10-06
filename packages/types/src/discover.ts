import { z } from "zod";

/**
 * 14-Dimensional Structured Filters parsed from natural language queries.
 */
export const StructuredDiscoverFiltersSchema = z.object({
  target: z.string().nullable().optional(),
  disease: z.string().nullable().optional(),
  indication: z.string().nullable().optional(),
  stage: z.array(z.string()).default([]),
  modality: z.string().nullable().optional(),
  biomarker: z.string().nullable().optional(),
  mutation: z.string().nullable().optional(),
  cns_requirement: z.boolean().nullable().optional(),
  clinical_evidence: z.boolean().nullable().optional(),
  safety: z.string().nullable().optional(),
  competition: z.string().nullable().optional(),
  ownership: z.string().nullable().optional(),
  licensing: z.string().nullable().optional(),
  commercial_opportunity: z.string().nullable().optional(),
});
export type StructuredDiscoverFilters = z.infer<typeof StructuredDiscoverFiltersSchema>;

/**
 * Canonical evidence citation attached to Discover match.
 */
export const DiscoverEvidenceItemSchema = z.object({
  evidence_id: z.string().optional(),
  type: z.string().default("LITERATURE"),
  citation: z.string(),
  url: z.string().nullable().optional(),
  polarity: z.string().default("SUPPORTING"),
  confidence: z.number().min(0).max(1).default(1.0),
});
export type DiscoverEvidenceItem = z.infer<typeof DiscoverEvidenceItemSchema>;

/**
 * Strictly formatted Ranked Candidate Match for Discover Engine.
 * Must expose: ranking, reason, evidence, confidence, and unknowns.
 */
export const RankedDiscoverMatchSchema = z.object({
  ranking: z.number().int().positive().describe("1-based integer ranking among matched candidates"),
  asset_id: z.string(),
  asset_name: z.string(),
  code_name: z.string().nullable().optional(),
  match_score: z.number().min(0).max(100).describe("Composite fit score (0-100)"),
  reason: z.string().describe("Explanatory scientific rationale for recommendation"),
  evidence: z.array(z.record(z.string(), z.unknown())).default([]).describe("Provenance-backed evidence items"),
  confidence: z.number().min(0).max(1).describe("AI inference certainty score"),
  unknowns: z.array(z.string()).default([]).describe("Explicit unknowns and evidence gaps"),

  // Supporting metadata
  primary_indication: z.string().default(""),
  stage: z.string().default(""),
  modality: z.string().default(""),
  owner: z.string().default(""),
});
export type RankedDiscoverMatch = z.infer<typeof RankedDiscoverMatchSchema>;

/**
 * Request payload for Discover Engine search.
 */
export const DiscoverQueryRequestSchema = z.object({
  query: z.string().min(1),
  explicit_filters: StructuredDiscoverFiltersSchema.nullable().optional(),
  top_k: z.number().int().positive().default(10),
});
export type DiscoverQueryRequest = z.infer<typeof DiscoverQueryRequestSchema>;

/**
 * Result payload containing query, parsed 14-dim filters, and ranked matches.
 */
export const DiscoverQueryResultSchema = z.object({
  id: z.string().uuid(),
  query: z.string(),
  parsed_filters: StructuredDiscoverFiltersSchema,
  results_count: z.number().int().nonnegative(),
  ranked_assets: z.array(RankedDiscoverMatchSchema),
  queried_at: z.string().datetime(),
});
export type DiscoverQueryResult = z.infer<typeof DiscoverQueryResultSchema>;
