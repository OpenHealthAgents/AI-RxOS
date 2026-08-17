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
