import { z } from "zod";

/** Shared domain types for the AI-RxOS platform. Mirrors architecture/03-api-contracts.md. */

export const UserSchema = z.object({
  id: z.string().uuid(),
  email: z.string().email(),
  displayName: z.string(),
  organizationId: z.string().uuid(),
  roles: z.array(z.string()),
  createdAt: z.string().datetime(),
});
export type User = z.infer<typeof UserSchema>;

export const OrganizationSchema = z.object({
  id: z.string().uuid(),
  name: z.string(),
  slug: z.string(),
  plan: z.enum(["free", "team", "enterprise"]),
});
export type Organization = z.infer<typeof OrganizationSchema>;

export const PaperSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  abstract: z.string().optional(),
  source: z.enum(["pubmed", "biorxiv", "medrxiv", "patent", "conference"]),
  doi: z.string().optional(),
  publishedAt: z.string().datetime().optional(),
  citationCount: z.number().int().nonnegative().default(0),
});
export type Paper = z.infer<typeof PaperSchema>;

export const GraphEntitySchema = z.object({
  id: z.string(),
  label: z.string(),
  type: z.enum(["gene", "protein", "disease", "drug", "pathway", "compound"]),
  properties: z.record(z.string(), z.unknown()).default({}),
});
export type GraphEntity = z.infer<typeof GraphEntitySchema>;

export const CanonicalEntityTypeSchema = z.enum([
  "therapeutic_asset",
  "target",
  "disease",
  "indication",
  "biomarker",
  "company",
  "clinical_trial",
  "publication",
  "patent",
  "regulatory_event",
  "mechanism",
  "combination",
  "resistance_mechanism",
]);
export type CanonicalEntityType = z.infer<typeof CanonicalEntityTypeSchema>;

export const TherapeuticModalitySchema = z.enum([
  "SMALL_MOLECULE",
  "ANTIBODY",
  "ADC",
  "PROTEIN",
  "PEPTIDE",
  "CELL_THERAPY",
  "GENE_THERAPY",
  "RNA_THERAPY",
  "RADIOPHARMACEUTICAL",
  "VACCINE",
  "OTHER",
]);
export type TherapeuticModality = z.infer<typeof TherapeuticModalitySchema>;

export const CanonicalSourceRecordSchema = z.object({
  namespace: z.string().min(1),
  external_id: z.string().min(1),
  source_type: z.enum([
    "publication",
    "trial_registry",
    "patent_registry",
    "regulatory_authority",
    "company",
    "database",
    "manual",
    "demo",
  ]),
  source_url: z.string().url().nullable().optional(),
  published_at: z.string().datetime().nullable().optional(),
  source_updated_at: z.string().datetime().nullable().optional(),
  observed_at: z.string().datetime().nullable().optional(),
  raw_payload_ref: z.string().nullable().optional(),
  content_hash: z.string().nullable().optional(),
  provenance: z.record(z.string(), z.unknown()).default({}),
});
export type CanonicalSourceRecord = z.infer<typeof CanonicalSourceRecordSchema>;

export const CanonicalIdentifierSchema = z.object({
  namespace: z.string().min(1),
  identifier_type: z.string().min(1),
  value: z.string().min(1),
  source_record: CanonicalSourceRecordSchema,
});
export type CanonicalIdentifier = z.infer<typeof CanonicalIdentifierSchema>;

export const CanonicalAliasSchema = z.object({
  value: z.string().min(1),
  alias_type: z.enum(["development", "generic", "brand", "alias", "synonym"]),
  verification_state: z.enum(["unreviewed", "verified", "rejected"]).default("unreviewed"),
  source_record: CanonicalSourceRecordSchema,
});
export type CanonicalAlias = z.infer<typeof CanonicalAliasSchema>;

export const CanonicalEntitySchema = z.object({
  id: z.string().uuid(),
  entity_type: CanonicalEntityTypeSchema,
  preferred_name: z.string(),
  normalized_name: z.string(),
  description: z.string().nullable().optional(),
  modality: TherapeuticModalitySchema.nullable().optional(),
  lifecycle_status: z.string().nullable().optional(),
  visibility: z.enum(["global", "tenant"]),
  organization_id: z.string().uuid().nullable().optional(),
  attributes: z.record(z.string(), z.unknown()).default({}),
  created_source_record_id: z.string().uuid().nullable().optional(),
  identifiers: z.array(z.record(z.string(), z.unknown())).default([]),
  aliases: z.array(z.record(z.string(), z.unknown())).default([]),
  created_at: z.string().datetime(),
  updated_at: z.string().datetime(),
});
export type CanonicalEntity = z.infer<typeof CanonicalEntitySchema>;

export const CanonicalEntityCreateSchema = z.object({
  entity_type: CanonicalEntityTypeSchema,
  preferred_name: z.string().min(1),
  description: z.string().nullable().optional(),
  modality: TherapeuticModalitySchema.nullable().optional(),
  lifecycle_status: z.string().nullable().optional(),
  visibility: z.enum(["global", "tenant"]).default("global"),
  attributes: z.record(z.string(), z.unknown()).default({}),
  source_record: CanonicalSourceRecordSchema,
  identifiers: z.array(CanonicalIdentifierSchema).default([]),
  aliases: z.array(CanonicalAliasSchema).default([]),
});
export type CanonicalEntityCreate = z.infer<typeof CanonicalEntityCreateSchema>;

export const CanonicalRelationshipCreateSchema = z.object({
  subject_entity_id: z.string().uuid(),
  predicate: z.string().regex(/^[A-Z][A-Z0-9_]{0,63}$/),
  object_entity_id: z.string().uuid(),
  visibility: z.enum(["global", "tenant"]).default("global"),
  attributes: z.record(z.string(), z.unknown()).default({}),
  source_record: CanonicalSourceRecordSchema,
  property_name: z.string().min(1).default("relationship_observed"),
  observation_value: z.unknown(),
  observation_kind: z.enum(["source_fact", "normalized_observation", "hypothesis"]).default("normalized_observation"),
  verification_state: z.enum(["unreviewed", "verified", "rejected"]).default("unreviewed"),
  confidence: z.number().min(0).max(1).nullable().optional(),
  valid_from: z.string().datetime().nullable().optional(),
  valid_to: z.string().datetime().nullable().optional(),
});
export type CanonicalRelationshipCreate = z.infer<typeof CanonicalRelationshipCreateSchema>;

export const CanonicalObservationSchema = z.object({
  id: z.string().uuid(),
  entity_id: z.string().uuid(),
  relationship_id: z.string().uuid().nullable().optional(),
  visibility: z.enum(["global", "tenant"]),
  property_name: z.string(),
  observation_kind: z.enum(["source_fact", "normalized_observation", "hypothesis"]),
  value: z.unknown(),
  verification_state: z.enum(["unreviewed", "verified", "rejected"]),
  confidence: z.number().min(0).max(1).nullable().optional(),
  valid_from: z.string().datetime().nullable().optional(),
  valid_to: z.string().datetime().nullable().optional(),
  published_at: z.string().datetime().nullable().optional(),
  observed_at: z.string().datetime().nullable().optional(),
  source_updated_at: z.string().datetime().nullable().optional(),
  ingested_at: z.string().datetime(),
  normalizer_version: z.string().nullable().optional(),
  supersedes_observation_id: z.string().uuid().nullable().optional(),
  manually_verified_by: z.string().uuid().nullable().optional(),
  manually_verified_at: z.string().datetime().nullable().optional(),
});
export type CanonicalObservation = z.infer<typeof CanonicalObservationSchema>;

export const CanonicalResolutionSchema = z.object({
  status: z.enum(["resolved", "ambiguous", "unresolved"]),
  entity: CanonicalEntitySchema.nullable().optional(),
  candidates: z.array(CanonicalEntitySchema).default([]),
});
export type CanonicalResolution = z.infer<typeof CanonicalResolutionSchema>;

export const MoleculeSchema = z.object({
  id: z.string().uuid(),
  smiles: z.string(),
  name: z.string().optional(),
  molecularWeight: z.number().optional(),
  logP: z.number().optional(),
});
export type Molecule = z.infer<typeof MoleculeSchema>;

export const DockingResultSchema = z.object({
  id: z.string().uuid(),
  moleculeId: z.string().uuid(),
  targetId: z.string(),
  bindingAffinity: z.number(),
  pose: z.string().optional(),
  status: z.enum(["queued", "running", "completed", "failed"]),
});
export type DockingResult = z.infer<typeof DockingResultSchema>;

export const AgentTaskSchema = z.object({
  id: z.string().uuid(),
  agentType: z.string(),
  input: z.record(z.string(), z.unknown()),
  status: z.enum(["pending", "running", "succeeded", "failed"]),
  result: z.record(z.string(), z.unknown()).optional(),
});
export type AgentTask = z.infer<typeof AgentTaskSchema>;

export const SearchResultSchema = z.object({
  id: z.string(),
  score: z.number(),
  // "pgvector" is retained for backward compatibility with existing
  // callers; services/search's actual retrieval providers are llm_wiki
  // (default) and google_okf — see services/search/internal/search/provider.go.
  source: z.enum(["opensearch", "pgvector", "llm_wiki", "google_okf", "graph"]),
  title: z.string(),
  snippet: z.string().optional(),
});
export type SearchResult = z.infer<typeof SearchResultSchema>;

/** Organization/workspace/project scope, mirroring packages/tenancy's
 * TENANT_ID_CLAIM convention and services/auth's AuthPayload shape. */
export const TenantScopeSchema = z.object({
  organizationId: z.string().optional(),
  workspaceId: z.string().optional(),
  projectId: z.string().optional(),
});
export type TenantScope = z.infer<typeof TenantScopeSchema>;

/** Canonical metadata attached to every LLM Wiki-indexed document/chunk. */
export const KnowledgeMetadataSchema = z.object({
  documentId: z.string(),
  sourceType: z.enum([
    "paper",
    "conference_abstract",
    "clinical_trial",
    "patent",
    "company",
    "drug_pipeline",
    "kg_derived",
    "agent_memory",
    "conversation",
  ]),
  sourceId: z.string(),
  title: z.string(),
  entityIds: z.array(z.string()).default([]),
  entityTypes: z.array(z.string()).default([]),
  version: z.number().int().positive().default(1),
  createdAt: z.string().datetime().optional(),
  updatedAt: z.string().datetime().optional(),
  provenance: z.record(z.string(), z.unknown()).default({}),
  citation: z.record(z.string(), z.unknown()).default({}),
}).merge(TenantScopeSchema);
export type KnowledgeMetadata = z.infer<typeof KnowledgeMetadataSchema>;

/** A chunk of an indexed document, traceable back to its source and tenant. */
export const ChunkSchema = z.object({
  chunkId: z.string(),
  chunkIndex: z.number().int().nonnegative(),
  text: z.string(),
  metadata: KnowledgeMetadataSchema,
});
export type Chunk = z.infer<typeof ChunkSchema>;

/** A single entry in an agent's scoped memory (services/agents). */
export const AgentMemoryEntrySchema = z.object({
  agentId: z.string(),
  key: z.string(),
  value: z.unknown(),
  provenance: z.record(z.string(), z.unknown()).default({}),
  storedAt: z.number().optional(),
}).merge(TenantScopeSchema);
export type AgentMemoryEntry = z.infer<typeof AgentMemoryEntrySchema>;

/** A single conversation turn (services/agents conversation memory). */
export const ConversationMessageSchema = z.object({
  role: z.enum(["user", "assistant", "system", "tool"]),
  content: z.string(),
  metadata: z.record(z.string(), z.unknown()).default({}),
  createdAt: z.number().optional(),
});
export type ConversationMessage = z.infer<typeof ConversationMessageSchema>;

export const ReportSchema = z.object({
  id: z.string().uuid(),
  title: z.string(),
  type: z.enum(["scientific", "competitive", "due-diligence", "executive"]),
  status: z.enum(["draft", "generating", "ready", "failed"]),
  createdAt: z.string().datetime(),
});
export type Report = z.infer<typeof ReportSchema>;

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export * from "./opportunity";
export * from "./canonical_domain";
export * from "./evidence";
export * from "./temporal";
export * from "./pubmed";
export * from "./clinicaltrials";
export * from "./regulatory";
export * from "./licensing";
export * from "./kg";
export * from "./discover";
export * from "./biology";
export * from "./cns";
export * from "./clinical";
export * from "./patient_match";
export * from "./resistance";
export * from "./combination";
export * from "./safety";
export * from "./competitive";
export * from "./commercial";
export * from "./resolution";
export * from "./provenance";
export * from "./contradiction";
export * from "./orchestration";
export * from "./search";
export * from "./ml";




