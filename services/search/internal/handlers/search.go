package handlers

import (
	"encoding/json"
	"net/http"
	"strconv"

	"github.com/openhealthagents/ai-rxos/services/search/internal/search"
)

type SearchHandler struct {
	OpenSearch   *search.Client
	Vectors      search.RetrievalProvider
	VectorSource string
	Citations    *search.CitationSearcher
	Graph        *search.GraphSearcher
	Ranker       *search.ResultRanker
}

type hybridRequest struct {
	Query          string    `json:"query"`
	Embedding      []float32 `json:"embedding,omitempty"`
	Limit          int       `json:"limit,omitempty"`
	OrganizationID string    `json:"organization_id,omitempty"`
	WorkspaceID    string    `json:"workspace_id,omitempty"`
}

func (r hybridRequest) tenant() search.TenantScope {
	return search.TenantScope{OrgID: r.OrganizationID, WorkspaceID: r.WorkspaceID}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// Query handles GET /api/v1/search?q=...&limit=... — keyword search via
// OpenSearch with optional citation authority enrichment.
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

	if h.Citations != nil {
		hits = h.Citations.EnrichHits(r.Context(), hits)
	}

	for i := range hits {
		if hits[i].Source == "" {
			hits[i].Source = "opensearch"
		}
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": hits, "total": len(hits), "page": 1, "pageSize": limit})
}

// Hybrid handles POST /api/v1/search — multi-signal hybrid retrieval across OpenSearch BM25,
// dense semantic vectors (LLM Wiki OKF QMD), Neo4j graph relationships, and citation networks,
// ranked by Reciprocal Rank Fusion (RRF).
func (h *SearchHandler) Hybrid(w http.ResponseWriter, r *http.Request) {
	var req hybridRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"code": "invalid_body", "message": err.Error()})
		return
	}
	if req.Limit <= 0 {
		req.Limit = 20
	}

	var bm25Hits []search.Hit
	var vectorHits []search.Hit

	if req.Query != "" {
		if hits, err := h.OpenSearch.Query(r.Context(), req.Query, req.Limit*2); err == nil {
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
		if hits, err := h.Vectors.SimilaritySearchForTenant(r.Context(), req.Embedding, req.Limit*2, req.tenant()); err == nil {
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

	ranked := ranker.RankRRF(req.Limit, bm25Hits, vectorHits)

	writeJSON(w, http.StatusOK, map[string]any{"items": ranked, "total": len(ranked), "page": 1, "pageSize": req.Limit})
}
