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
	topK := req.TopK
	if topK <= 0 {
		topK = 10
	}
	maxSnippet := req.MaxSnippetChars
	if maxSnippet <= 0 {
		maxSnippet = 320
	}

	var bm25Hits []search.Hit
	var vectorHits []search.Hit

	if req.Query != "" && h.OpenSearch != nil {
		if hits, err := h.OpenSearch.Query(r.Context(), req.Query, topK*2); err == nil {
			for i := range hits {
				if hits[i].Source == "" {
					hits[i].Source = "opensearch"
				}
			}
			bm25Hits = hits
		}
	}

	if len(req.Embedding) > 0 && h.Vectors != nil {
		source := h.VectorSource
		if source == "" {
			source = search.ProviderLLMWiki
		}
		if hits, err := h.Vectors.SimilaritySearchForTenant(r.Context(), req.Embedding, topK*2, req.tenant()); err == nil {
			for i := range hits {
				if hits[i].Source == "" {
					hits[i].Source = source
				}
			}
			vectorHits = hits
		}
	}

	if h.Citations != nil {
		bm25Hits = h.Citations.EnrichHits(r.Context(), bm25Hits)
		vectorHits = h.Citations.EnrichHits(r.Context(), vectorHits)
	}
	if h.Graph != nil {
		bm25Hits = h.Graph.EnrichHits(r.Context(), req.Query, bm25Hits)
		vectorHits = h.Graph.EnrichHits(r.Context(), req.Query, vectorHits)
	}

	ranker := h.Ranker
	if ranker == nil {
		ranker = search.NewResultRanker(60, 0.35, 0.35, 0.15, 0.15)
	}
	ranked := ranker.RankRRF(topK*2, bm25Hits, vectorHits)
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
