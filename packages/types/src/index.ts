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
  source: z.enum(["opensearch", "pgvector", "graph"]),
  title: z.string(),
  snippet: z.string().optional(),
});
export type SearchResult = z.infer<typeof SearchResultSchema>;

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
