import type {
  AgentTask,
  DockingResult,
  Molecule,
  Paginated,
  Paper,
  Report,
  SearchResult,
} from "@ai-rxos/types";
import type { AiRxOsClient } from "./client";

/** Thin typed wrappers over api-gateway routes. See architecture/03-api-contracts.md. */

export const search = (client: AiRxOsClient) => ({
  query: (q: string, limit = 20) =>
    client.get<Paginated<SearchResult>>(`/api/v1/search?q=${encodeURIComponent(q)}&limit=${limit}`),
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
  run: (agentType: string, input: Record<string, unknown>) =>
    client.post<AgentTask>(`/api/v1/agents/run`, { agentType, input }),
  get: (id: string) => client.get<AgentTask>(`/api/v1/agents/tasks/${id}`),
});

export const reports = (client: AiRxOsClient) => ({
  list: (page = 1) => client.get<Paginated<Report>>(`/api/v1/reports?page=${page}`),
  generate: (title: string, type: Report["type"]) =>
    client.post<Report>(`/api/v1/reports`, { title, type }),
});
