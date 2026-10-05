package handlers

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

// contextRequest is the input to POST /api/v1/search/context — the Prompt 8
// context-optimization endpoint. It reuses the same retrieval/ranking legs
// as Hybrid (OpenSearch BM25 + LLM Wiki/QMD vector + graph/citation
// enrichment + RRF), but trims the output to compact, cited snippets
// instead of full documents, and supports the filters/scoping a caller
// building agent or conversation context needs.
type contextRequest struct {
	Query          string    `json:"query"`
	Embedding      []float32 `json:"embedding,omitempty"`
	TopK           int       `json:"top_k,omitempty"`
	SourceFilters  []string  `json:"source_filters,omitempty"`
	EntityFilters  []string  `json:"entity_filters,omitempty"`
	OrganizationID string    `json:"organization_id,omitempty"`
	WorkspaceID    string    `json:"workspace_id,omitempty"`
	ProjectID      string    `json:"project_id,omitempty"`
	ConversationID string    `json:"conversation_id,omitempty"`
	AgentID        string    `json:"agent_id,omitempty"`
	AsOf           string    `json:"as_of,omitempty"`
	// MaxSnippetChars caps each returned snippet's length (default 320).
	// The point of this endpoint is compact context, not full documents.
	MaxSnippetChars int `json:"max_snippet_chars,omitempty"`
}

func (r contextRequest) tenant() search.TenantScope {
	return search.TenantScope{OrgID: r.OrganizationID, WorkspaceID: r.WorkspaceID}
}

// contextItem is a single piece of retrieved context: a compact snippet
// plus enough provenance/citation metadata to trace it back to its source,
// never the full source document.
type contextItem struct {
	ID       string  `json:"id"`
	Title    string  `json:"title"`
	Snippet  string  `json:"snippet"`
	Source   string  `json:"source"`
	Score    float64 `json:"score"`
	Citation string  `json:"citation"`
}

// Context handles POST /api/v1/search/context — builds compact, cited
// context for agent/conversation consumption from the same hybrid
// retrieval pipeline Hybrid uses, rather than a second ranking engine.
func (h *SearchHandler) Context(w http.ResponseWriter, r *http.Request) {
	var req contextRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": err.Error()})
		return
	}
	if req.Query == "" && len(req.Embedding) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "missing_query", "message": "query or embedding is required"})
		return
	}
	tenant, ok := requireRequestScope(w, r)
	if !ok {
		return
	}
	topK := req.TopK
	if topK <= 0 {
		topK = 10
	}
	maxSnippet := req.MaxSnippetChars
	if maxSnippet <= 0 {
		maxSnippet = 320
	}
	asOf, err := parseAsOf(req.AsOf)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_as_of", "message": "as_of must be an RFC3339 timestamp"})
		return
	}

	var bm25Hits []search.Hit
	var vectorHits []search.Hit
	queryOptions := search.QueryOptions{
		Query: req.Query, Page: 1, PageSize: topK * 2,
		EntityTypes: req.EntityFilters, Sources: req.SourceFilters, AsOf: asOf,
	}

	if req.Query != "" && h.OpenSearch != nil {
		result, err := h.OpenSearch.QueryWithOptionsForTenant(r.Context(), queryOptions, tenant)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "keyword_search_failed", "message": err.Error()})
			return
		}
		bm25Hits = result.Hits
	}

	if len(req.Embedding) > 0 && h.OpenSearch != nil {
		hits, err := h.OpenSearch.SemanticSearchWithOptionsForTenant(r.Context(), req.Embedding, queryOptions, tenant)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "semantic_search_failed", "message": err.Error()})
			return
		}
		vectorHits = hits
	}

	if h.Citations != nil {
		bm25Hits = h.Citations.EnrichHits(r.Context(), bm25Hits)
		vectorHits = h.Citations.EnrichHits(r.Context(), vectorHits)
	}
	if h.Graph != nil {
		var err error
		bm25Hits, err = h.Graph.EnrichHits(r.Context(), req.Query, bm25Hits, r.Header.Get("Authorization"))
		if err == nil {
			vectorHits, err = h.Graph.EnrichHits(r.Context(), req.Query, vectorHits, r.Header.Get("Authorization"))
		}
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "graph_enrichment_failed", "message": err.Error()})
			return
		}
	}

	ranker := h.Ranker
	if ranker == nil {
		ranker = search.NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	}
	ranked := ranker.RankRRF(topK*2, bm25Hits, vectorHits)
	if h.Canonical != nil {
		ranked, err = h.Canonical.EnrichHits(r.Context(), ranked, r.Header.Get("Authorization"), asOf)
		if err != nil {
			writeJSON(w, http.StatusBadGateway, map[string]string{"code": "canonical_context_failed", "message": err.Error()})
			return
		}
	}
	ranked = applyContextFilters(ranked, req.SourceFilters, req.EntityFilters)
	if len(ranked) > topK {
		ranked = ranked[:topK]
	}

	items := make([]contextItem, 0, len(ranked))
	for _, hit := range ranked {
		items = append(items, contextItem{
			ID:       hit.ID,
			Title:    hit.Title,
			Snippet:  truncateSnippet(hit.Snippet, maxSnippet),
			Source:   hit.Source,
			Score:    hit.Score,
			Citation: hit.Title,
		})
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"items": items,
		"total": len(items),
		"scope": map[string]string{
			"organization_id": req.OrganizationID,
			"workspace_id":    req.WorkspaceID,
			"project_id":      req.ProjectID,
			"conversation_id": req.ConversationID,
			"agent_id":        req.AgentID,
		},
	})
}

func applyContextFilters(hits []search.Hit, sourceFilters, entityFilters []string) []search.Hit {
	if len(sourceFilters) == 0 && len(entityFilters) == 0 {
		return hits
	}
	sourceSet := make(map[string]bool, len(sourceFilters))
	for _, s := range sourceFilters {
		sourceSet[strings.ToLower(s)] = true
	}

	filtered := make([]search.Hit, 0, len(hits))
	for _, hit := range hits {
		if len(sourceFilters) > 0 && !sourceSet[strings.ToLower(hit.Source)] {
			continue
		}
		if len(entityFilters) > 0 {
			haystack := strings.ToLower(hit.Title + " " + hit.Snippet)
			matched := false
			for _, entity := range entityFilters {
				if strings.Contains(haystack, strings.ToLower(entity)) {
					matched = true
					break
				}
			}
			if !matched {
				continue
			}
		}
		filtered = append(filtered, hit)
	}
	return filtered
}

func truncateSnippet(snippet string, maxChars int) string {
	if len(snippet) <= maxChars {
		return snippet
	}
	return strings.TrimSpace(snippet[:maxChars]) + "..."
}
