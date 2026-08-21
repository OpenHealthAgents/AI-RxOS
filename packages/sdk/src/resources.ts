import type {
  AgentMemoryEntry,
  AgentTask,
  ConversationMessage,
  DockingResult,
  Molecule,
  Paginated,
  Paper,
  Report,
  SearchResult,
  TenantScope,
} from "@ai-rxos/types";
import type { AiRxOsClient } from "./client";

/** Thin typed wrappers over api-gateway routes. See architecture/03-api-contracts.md. */

export interface ContextItem {
  id: string;
  title: string;
  snippet: string;
  source: string;
  score: number;
  citation: string;
}

export interface ContextRequest extends TenantScope {
  query?: string;
  embedding?: number[];
  topK?: number;
  sourceFilters?: string[];
  entityFilters?: string[];
  conversationId?: string;
  agentId?: string;
}

export const search = (client: AiRxOsClient) => ({
  query: (q: string, limit = 20) =>
    client.get<Paginated<SearchResult>>(`/api/v1/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  /** Prompt 8 context-optimization endpoint: compact, cited context instead
   * of full documents. See services/search/internal/handlers/context.go. */
  context: (req: ContextRequest) =>
    client.post<{ items: ContextItem[]; total: number }>(`/api/v1/search/context`, {
      query: req.query,
      embedding: req.embedding,
      top_k: req.topK,
      source_filters: req.sourceFilters,
      entity_filters: req.entityFilters,
      organization_id: req.organizationId,
      workspace_id: req.workspaceId,
      project_id: req.projectId,
      conversation_id: req.conversationId,
      agent_id: req.agentId,
    }),
});

export const literature = (client: AiRxOsClient) => ({
  list: (page = 1) => client.get<Paginated<Paper>>(`/api/v1/papers?page=${page}`),
  get: (id: string) => client.get<Paper>(`/api/v1/papers/${id}`),
});

export const molecules = (client: AiRxOsClient) => ({
  list: (page = 1) => client.get<Paginated<Molecule>>(`/api/v1/molecules?page=${page}`),
  dock: (moleculeId: string, targetId: string) =>
    client.post<DockingResult>(`/api/v1/docking`, { moleculeId, targetId }),
});

export const agents = (client: AiRxOsClient) => ({
  // services/agents exposes POST /api/v1/agents/invoke (see
  // services/agents/app/main.py) — not /run, which was a pre-existing SDK/
  // service mismatch fixed alongside the memory/conversation additions below.
  run: (agentType: string, input: Record<string, unknown>) =>
    client.post<AgentTask>(`/api/v1/agents/invoke`, { agentType, input }),
  get: (id: string) => client.get<AgentTask>(`/api/v1/agents/tasks/${id}`),
});

/** Agent memory (Prompt 8): store/retrieve/search agent-scoped memory.
 * See services/agents/app/routers/memory.py. Tenant scoping is derived
 * server-side from the caller's auth token, not from these arguments. */
export const agentMemory = (client: AiRxOsClient) => ({
  store: (agentId: string, key: string, value: unknown, opts?: { provenance?: Record<string, unknown>; persistLongTerm?: boolean }) =>
    client.post<AgentMemoryEntry>(`/api/v1/agents/memory`, {
      agent_id: agentId,
      key,
      value,
      provenance: opts?.provenance ?? {},
      persist_long_term: opts?.persistLongTerm ?? false,
    }),
  retrieve: (agentId: string, key: string) =>
    client.get<AgentMemoryEntry>(`/api/v1/agents/memory/${agentId}/${encodeURIComponent(key)}`),
  search: (agentId: string, query?: string, limit = 10) =>
    client.get<{ items: AgentMemoryEntry[]; total: number }>(
      `/api/v1/agents/memory/${agentId}?${query ? `query=${encodeURIComponent(query)}&` : ""}limit=${limit}`,
    ),
});

/** Conversation memory (Prompt 8). See services/agents/app/routers/conversations.py. */
export const conversations = (client: AiRxOsClient) => ({
  addMessage: (conversationId: string, message: Omit<ConversationMessage, "createdAt">) =>
    client.post<{ messages: ConversationMessage[] }>(
      `/api/v1/agents/conversations/${conversationId}/messages`,
      message,
    ),
  getMessages: (conversationId: string, limit?: number) =>
    client.get<{ conversationId: string; messages: ConversationMessage[]; total: number }>(
      `/api/v1/agents/conversations/${conversationId}/messages${limit ? `?limit=${limit}` : ""}`,
    ),
});

export const reports = (client: AiRxOsClient) => ({
  list: (page = 1) => client.get<Paginated<Report>>(`/api/v1/reports?page=${page}`),
  generate: (title: string, type: Report["type"]) =>
    client.post<Report>(`/api/v1/reports`, { title, type }),
});
