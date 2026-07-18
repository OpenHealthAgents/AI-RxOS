package handlers

import (
	"encoding/json"
	"net/http"
	"sort"
	"strconv"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

type SearchHandler struct {
	OpenSearch *search.Client
	Vectors    search.RetrievalProvider
	// VectorSource labels the "source" field of hits returned by Vectors,
	// reflecting whichever provider is configured (see
	// internal/search/provider.go). Defaults to "pgvector" when unset.
	VectorSource string
}

type searchResult struct {
	ID      string  `json:"id"`
	Score   float64 `json:"score"`
	Source  string  `json:"source"`
	Title   string  `json:"title"`
	Snippet string  `json:"snippet"`
}

type hybridRequest struct {
	Query     string    `json:"query"`
	Embedding []float32 `json:"embedding,omitempty"`
	Limit     int       `json:"limit,omitempty"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// Query handles GET /api/v1/search?q=...&limit=... — keyword search via
// OpenSearch. Use POST /api/v1/search for hybrid keyword + pgvector search.
func (h *SearchHandler) Query(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query().Get("q")
	limit, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if limit <= 0 {
		limit = 20
	}
	if q == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "missing_query", "message": "q is required"})
		return
	}

	hits, err := h.OpenSearch.Query(r.Context(), q, limit)
	if err != nil {
		writeJSON(w, http.StatusBadGateway, map[string]string{"code": "opensearch_error", "message": err.Error()})
		return
	}

	items := make([]searchResult, 0, len(hits))
	for _, hit := range hits {
		items = append(items, searchResult{ID: hit.ID, Score: hit.Score, Source: "opensearch", Title: hit.Title, Snippet: hit.Snippet})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": len(items), "page": 1, "pageSize": limit})
}

// Hybrid handles POST /api/v1/search — merges OpenSearch keyword results
// with pgvector cosine-similarity results (when an embedding is supplied),
// ranked by score.
func (h *SearchHandler) Hybrid(w http.ResponseWriter, r *http.Request) {
	var req hybridRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": err.Error()})
		return
	}
	if req.Limit <= 0 {
		req.Limit = 20
	}

	var items []searchResult

	if req.Query != "" {
		hits, err := h.OpenSearch.Query(r.Context(), req.Query, req.Limit)
		if err == nil {
			for _, hit := range hits {
				items = append(items, searchResult{ID: hit.ID, Score: hit.Score, Source: "opensearch", Title: hit.Title, Snippet: hit.Snippet})
			}
		}
	}

	if len(req.Embedding) > 0 && h.Vectors != nil {
		source := h.VectorSource
		if source == "" {
			source = search.ProviderPgvector
		}
		hits, err := h.Vectors.SimilaritySearch(r.Context(), req.Embedding, req.Limit)
		if err == nil {
			for _, hit := range hits {
				items = append(items, searchResult{ID: hit.ID, Score: hit.Score, Source: source, Title: hit.Title, Snippet: hit.Snippet})
			}
		}
	}

	sort.Slice(items, func(i, j int) bool { return items[i].Score > items[j].Score })
	if len(items) > req.Limit {
		items = items[:req.Limit]
	}

	writeJSON(w, http.StatusOK, map[string]any{"items": items, "total": len(items), "page": 1, "pageSize": req.Limit})
}
